# WorkspaceMenu

The two menus in the sidebar, plus the dialogs they open. The workspace block at the top switches workspaces, creates one, and resets the demo workspace. The Account button at the bottom shows who is signed in and signs out.

**Use it** in every page that has the app shell. `FTWorkspaceMenu.attach(options)` finds the sidebar's `.ft-workspace` block and its Account button, turns them into menu buttons, and needs no other markup.

| Option | What it is |
|---|---|
| `workspaces` | `[{id, name, note, demo}]`. `note` is the quiet line under the name. `demo: true` adds Reset demo workspace. |
| `current` | The current workspace's `id` |
| `user` | `{name, email}` for the Account menu |
| `onNavigate(kind, value)` | `'workspace'` (id), `'new'` (name), `'reset'` (id) or `'signout'`. Return `false` to skip the default, which only updates the workspace button's label. |

`FTWorkspaceMenu.open('workspace' | 'account')`, `.dialog('new' | 'reset')` and `.close()` open states directly.

**Menus.**
- The workspace menu opens below its block, and the Account menu opens above its button.
- The current workspace has a check. The destructive item, Reset demo workspace, is the last item in `reject` red, and only the demo workspace has it.
- The Account menu names the user, their email and "Signed in with Google", then Sign out.

**Dialogs.** A centered `ft-dialog` over the scrim, `radius-lg` and `shadow-float`, with Cancel left of the main action.
- **New workspace:** a Name field. An empty name gets "Add a name." A taken name gets "You already have a workspace with that name."
- **Reset demo workspace:** an `alertdialog` that lists what the reset clears. It opens with focus on Cancel, and its action is a `ft-btn--reject` "Reset workspace".

**Keyboard.**
- The menu buttons follow the menu button pattern. Enter, Space or Down opens on the first item (the checked workspace when there is one), and Up opens on the last.
- In a menu, the arrows, Home and End move between items, and typing a letter jumps to an item.
- Esc closes and returns focus to the button. Tab closes too, and so do a click outside the menu or choosing an item.
- In a dialog, focus stays inside, Esc or the scrim cancels, and focus returns to the workspace button. The page behind is inert while a dialog is open.

**Proposals, not decided in docs/product.md:**
- What a reset clears: the user's answers, confirmations, splits, sign-offs and files, and the clock goes back to the demo's start. Other workspaces don't change.
- Creating extra workspaces is optional scope.

**Hash params, for screenshots:** `#open=workspace`, `#open=account`, `#dialog=new` (add `&err=1` for the empty-name error), `#dialog=reset`, `#t=dark`.

Don't: put Reset or Sign out anywhere a stray click can trigger it without a menu, or confirm a reset without listing what it clears.
