# PropertyAIgent access handover

User instruction recorded 29 September 2026:

- Render and Supabase: first check for and reuse an existing authenticated browser session. Do not log out or switch accounts merely to change authentication methods.
- If logged out, the user explicitly authorises routine **Continue with GitHub** sign-in through their existing GitHub account for both Render and Supabase.
- GitHub: reuse an existing authenticated session; if credentials or verification are needed, use supported secure sign-in or user handoff. Never request secret values in chat.
- Staying signed in and saving a password are distinct. This instruction does not assert that either persists, or request enabling password storage.
- Never record passwords, tokens, cookies or verification codes in chat, repository or reports. This note records the method and permission only.
- Verify authenticated access each session; do not assume sessions or saved passwords persist.
- Login permission does not authorise new OAuth scopes, expanded permissions, production writes, migration, deployment, billing changes or release.

Future collaborators should read this alongside current task instructions. This local repository note does not automatically propagate to every separate chat or remote checkout. No push is authorised.
