"""The agent's graph, in LangGraph, and the one function the rest of the backend calls.

    prepare ─► model ─► act ─┐
                 ▲           │ tool results and write problems
                 └───────────┘
                 │ finish, or a turn with no tool call and no label lines
                 ▼
               gate ── an open question for the agent ──► back to model, with the list
                 │ none
                 ▼
               save ─► RunSaved (W4 saves it in one transaction)

- prepare builds the first message (the desk).
- model calls claude-opus-5-5 with the whole history.
- act runs each tool call. A turn with label lines and no tool call gets code's reply with the
  labels it recorded, and the loop goes on.
- gate runs the checks on the database plus the staged records. For a thread run it covers only
  the thread's charge or record; other open questions are reported so W4 queues an ordinary run.
- save rechecks every staged write in order and hands back the records to save.

Any failure (an API error, a refusal, too many turns) gives RunFailed, and nothing is saved.
LangGraph's mid-run saving is off, so a crashed run starts over.
"""

from collections.abc import Hashable
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from .adapter import (
    TRIGGER_CHARGE,
    TRIGGER_CLOCK,
    TRIGGER_THREAD,
    Author,
    BudgetAssignment,
    Judgment,
    OpenQuestion,
    Question,
    agent_questions,
    check_write,
)
from .citations import LabelLine, parse_label_lines
from .context import RunContext
from .desk import first_message
from .inputs import RunFailed, RunInputs, RunResult, RunSaved
from .model import (
    MAX_TOKENS,
    MAX_TOKENS_RETRY,
    MODEL,
    AnthropicModel,
    ModelClient,
    ModelRequest,
    is_retryable,
)
from .prompts import SYSTEM_PROMPT
from .rulebook import load_rulebook
from .tools import run_tool, tool_definitions

MAX_TURNS = 60
MAX_TURNS_CLOSEOUT = 150
MAX_GATE_RETURNS = 3


class State(TypedDict):
    ctx: RunContext


def _fail(ctx: RunContext, error: str, retryable: bool) -> None:
    ctx.failure = (error, retryable)
    ctx.log_event("failed", error=error, retryable=retryable)
    ctx.next = "end"


def system_blocks(ctx: RunContext) -> list[dict[str, Any]]:
    return [
        {"type": "text", "text": SYSTEM_PROMPT},
        {
            "type": "text",
            "text": f"# The {ctx.rulebook.funder} rulebook\n\n{ctx.rulebook.text}",
            "cache_control": {"type": "ephemeral"},
        },
    ]


def build_graph(model: ModelClient) -> Any:
    tools = tool_definitions()

    def prepare(state: State) -> State:
        ctx = state["ctx"]
        ctx.start_log(system_blocks(ctx), tools, MODEL, "high")
        content = first_message(ctx)
        ctx.messages.append({"role": "user", "content": content})
        ctx.log_event("first_message", content=content)
        ctx.next = "model"
        return state

    def call_model(state: State) -> State:
        ctx = state["ctx"]
        limit = MAX_TURNS_CLOSEOUT if ctx.inputs.trigger.kind == TRIGGER_CLOCK else MAX_TURNS
        if ctx.turns >= limit:
            _fail(ctx, f"the run took more than {limit} model turns", False)
            return state
        ctx.turns += 1
        request = ModelRequest(
            system=system_blocks(ctx),
            tools=tools,
            messages=ctx.messages,
            max_tokens=MAX_TOKENS_RETRY if ctx.max_tokens_retried else MAX_TOKENS,
        )
        try:
            message = model(request)
        except Exception as error:  # the SDK's typed errors, and anything unexpected
            _fail(
                ctx, f"the model call failed: {type(error).__name__}: {error}", is_retryable(error)
            )
            return state
        ctx.add_usage(message.usage)
        ctx.log_event("response", message=message)
        if message.stop_reason == "refusal":
            _fail(
                ctx,
                "the model declined the request (a safety refusal); no other model is used",
                False,
            )
            return state
        if message.stop_reason == "max_tokens":
            if ctx.max_tokens_retried:
                _fail(ctx, "the model hit its output limit twice in one turn", False)
                return state
            # Ask again once with a larger limit; the cut turn is dropped.
            ctx.max_tokens_retried = True
            ctx.turns -= 1
            ctx.next = "model"
            return state
        if message.stop_reason in ("pause_turn", "model_context_window_exceeded"):
            _fail(ctx, f"the model stopped with {message.stop_reason}, which isn't a finish", False)
            return state
        ctx.max_tokens_retried = False  # the larger limit is for one retried turn only
        ctx.messages.append({"role": "assistant", "content": message.content})
        lines = parse_label_lines(message.content)
        recorded, refused = record_labels(ctx, lines)
        uses = [b for b in message.content if b.type == "tool_use"]
        ctx.label_note = label_note(refused)
        if uses:
            ctx.next = "act"
            if lines:
                ctx.log_event("labels", labels={ln.label: bool(ln.citations) for ln in recorded})
            return state
        if lines:
            cited = [ln.label for ln in recorded if ln.citations]
            uncited = [ln.label for ln in recorded if not ln.citations]
            reply = "Recorded with citations: " + (", ".join(cited) or "none") + "."
            if uncited:
                reply += (
                    " Came back with no citation: "
                    + ", ".join(uncited)
                    + ". Write those again citing the file, or leave them out."
                )
            reply += ctx.label_note
            ctx.label_note = ""
            ctx.log_event("labels", reply=reply)
            ctx.messages.append({"role": "user", "content": reply})
            ctx.next = "model"
            return state
        ctx.next = "gate"
        return state

    def act(state: State) -> State:
        ctx = state["ctx"]
        last = ctx.messages[-1]["content"]
        results: list[dict[str, Any]] = []
        finish_id: str | None = None
        for block in last:
            if getattr(block, "type", None) != "tool_use":
                continue
            if block.name == "finish":
                finish_id = block.id
                ctx.summary = str((block.input or {}).get("summary") or "").strip() or ctx.summary
                continue
            content, is_error = run_tool(ctx, block.name, block.input)
            ctx.log_event(
                "tool", name=block.name, input=block.input, result=content, is_error=is_error
            )
            result: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": content,
            }
            if is_error:
                result["is_error"] = True
            results.append(result)
        if finish_id is not None and any(r.get("is_error") for r in results):
            # A refused write in the finishing turn goes back to the model, not to the gate.
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": finish_id,
                    "content": "Not finished: a write in this turn was refused. Fix it or leave "
                    "it out, then call finish again.",
                    "is_error": True,
                }
            )
            finish_id = None
            ctx.summary = None
            note: list[dict[str, Any]] = (
                [{"type": "text", "text": ctx.label_note.strip()}] if ctx.label_note else []
            )
            ctx.label_note = ""
            ctx.messages.append({"role": "user", "content": [*results, *note]})
            ctx.next = "model"
        elif finish_id is not None:
            ctx.pending_finish_id = finish_id
            ctx.pending_results = results
            ctx.next = "gate"
        else:
            ctx.messages.append({"role": "user", "content": results})
            ctx.next = "model"
        return state

    def gate(state: State) -> State:
        ctx = state["ctx"]
        waiting, _ = split_questions(ctx)
        unassigned = charges_without_budget_line(ctx)
        ctx.log_event(
            "gate",
            waiting=[q.model_dump(mode="json") for q in waiting],
            no_budget_line=unassigned,
        )
        if not waiting and not unassigned:
            ctx.next = "save"
            return state
        ctx.gate_returns += 1
        if ctx.gate_returns > MAX_GATE_RETURNS:
            _fail(
                ctx,
                f"work still waited for the agent after {MAX_GATE_RETURNS} returns",
                False,
            )
            return state
        text = "The run can't end yet."
        if waiting:
            text += " These questions code asked still wait for your answer:\n" + "\n".join(
                f"- {q.question} on charge {q.charge_id}"
                + (f" about {q.record_id}" if q.record_id else "")
                for q in waiting
            )
            text += "\nAnswer each one (unsure is allowed)."
        if unassigned:
            text += (
                "\nThese charges have no budget line yet: "
                + ", ".join(unassigned)
                + ". Assign each one with assign_budget_line, or flag the charge if you can't tell."
            )
        text += "\nThen finish."
        if ctx.pending_finish_id is not None:
            results = [
                *ctx.pending_results,
                {
                    "type": "tool_result",
                    "tool_use_id": ctx.pending_finish_id,
                    "content": text,
                    "is_error": True,
                },
            ]
            ctx.messages.append({"role": "user", "content": results})
            ctx.pending_finish_id, ctx.pending_results = None, []
        else:
            ctx.messages.append({"role": "user", "content": text})
        ctx.next = "model"
        return state

    def save(state: State) -> State:
        ctx = state["ctx"]
        problems = recheck(ctx)
        if problems:
            _fail(
                ctx, "a staged write no longer passes the write check: " + " ".join(problems), True
            )
            return state
        ctx.next = "end"
        return state

    graph = StateGraph(State)
    graph.add_node("prepare", prepare)
    graph.add_node("model", call_model)
    graph.add_node("act", act)
    graph.add_node("gate", gate)
    graph.add_node("save", save)
    graph.set_entry_point("prepare")
    routes: dict[Hashable, str] = {
        "model": "model",
        "act": "act",
        "gate": "gate",
        "save": "save",
        "end": END,
    }
    for node in ("prepare", "model", "act", "gate"):
        graph.add_conditional_edges(node, lambda s: s["ctx"].next, routes)
    graph.add_edge("save", END)
    return graph.compile()


def record_labels(ctx: RunContext, lines: list[LabelLine]) -> tuple[list[LabelLine], list[str]]:
    """Add a turn's label lines to the run's table. A label already used with a citation is
    refused, not overwritten; one that came back uncited can be written again."""
    recorded: list[LabelLine] = []
    refused: list[str] = []
    seen: set[str] = set()
    for line in lines:
        earlier = ctx.labels.get(line.label)
        if line.label in seen or (earlier is not None and earlier.citations):
            refused.append(line.label)
            continue
        seen.add(line.label)
        ctx.labels[line.label] = line
        recorded.append(line)
    return recorded, refused


def label_note(refused: list[str]) -> str:
    if not refused:
        return ""
    return (
        " Already used in this run, so not recorded again: "
        + ", ".join(dict.fromkeys(refused))
        + ". Write each of those lines under a new label."
    )


def split_questions(ctx: RunContext) -> tuple[list[OpenQuestion], list[OpenQuestion]]:
    """The open questions this run's gate covers, and the rest.

    An ordinary run covers every open question waiting for the agent on the grant. A thread run
    replies and suggests, and covers none (the main coordinator's ruling, replacing answer 3):
    every open question, the thread's own charge included, goes back to the platform, which
    queues an ordinary run, and the reply isn't held up.
    """
    questions = agent_questions(ctx.checks())
    if ctx.inputs.trigger.kind == TRIGGER_THREAD:
        return [], questions
    return questions, []


def charges_without_budget_line(ctx: RunContext) -> list[str]:
    """The charges this run covers that have neither a budget line nor the agent's flag.

    A charge run covers its batch of charges. The run can't finish until each has a current
    budget assignment, or a current flag of the agent's saying it can't tell (the main
    coordinator's ruling).
    """
    i = ctx.inputs
    if i.trigger.kind != TRIGGER_CHARGE:
        return []
    covered = list(i.charge_ids) or ([i.trigger.id] if i.trigger.id else [])
    current = ctx.state().current()
    assigned = {r.charge_id for r in current if isinstance(r.data, BudgetAssignment)}
    flagged = {
        r.charge_id
        for r in current
        if isinstance(r.data, Judgment)
        and r.data.question == Question.FLAG
        and r.author == Author.AGENT
    }
    return [c for c in covered if c not in assigned and c not in flagged]


def recheck(ctx: RunContext) -> list[str]:
    """Every staged write checked again, in order, against the inputs and the writes before it."""
    i = ctx.inputs
    written = list(i.records)
    problems: list[str] = []
    for staged in ctx.staged:
        found = check_write(staged.record, written, i.charges, i.files, i.default_items, i.trigger)
        problems += [f"{staged.record.id}: {p}" for p in found]
        written.append(staged.record)
    return problems


def recheck_before_save(result: RunSaved, inputs: RunInputs) -> list[str]:
    """For W4, inside its save transaction with the database's records as they are now.

    `inputs` holds the fresh records, charges and files. Any problem means the accountant changed
    something meanwhile: drop the whole run and queue it again, so nothing half-applies.
    """
    written = list(inputs.records)
    problems: list[str] = []
    for record in result.records:
        found = check_write(
            record, written, inputs.charges, inputs.files, inputs.default_items, inputs.trigger
        )
        problems += [f"{record.id}: {p}" for p in found]
        written.append(record)
    return problems


def run_once(inputs: RunInputs, model: ModelClient | None = None) -> RunResult:
    """Run the agent once: the records to save, or a failure. Saving and queuing are W4's."""
    ctx = RunContext(inputs=inputs, rulebook=load_rulebook(inputs.funder))
    graph = build_graph(model or AnthropicModel())
    try:
        graph.invoke({"ctx": ctx}, config={"recursion_limit": 4 * MAX_TURNS_CLOSEOUT + 20})
    except Exception as error:  # a bug in a tool or the graph: the run fails and saves nothing
        _fail(ctx, f"the run stopped on an error: {type(error).__name__}: {error}", False)
    if ctx.failure is not None:
        error, retryable = ctx.failure
        ctx.log["outcome"] = "failed"
        return RunFailed(
            error=error,
            retryable=retryable,
            trigger=inputs.trigger,
            log=ctx.log,
            log_path=ctx.log_path,
        )
    _, others = split_questions(ctx)
    ctx.log["outcome"] = "saved"
    return RunSaved(
        records=[s.record for s in ctx.staged],
        messages=ctx.messages_out,
        summary=ctx.summary or "The agent finished without a summary.",
        other_open_questions=others,
        log=ctx.log,
        log_path=ctx.log_path,
    )
