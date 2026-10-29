# Agent Rules

> [!IMPORTANT]
> **💡 File Insight & Purpose**:
> - **Role in Library**: Operational constraints & guardrails for AI coding assistants.
> - **What is happening here**: Enforces absolute data integrity—prohibiting agents from fabricating cultural/linguistic claims, touching data directories unprompted, or inventing sources/consents.
> - **Who should use it**: AI agents and automated tools operating on this repository.

- Never write cultural, historical or linguistic facts, meanings, translations, song lyrics, names of people or organizations, or consent/permission records. Only the human maintainer adds these.
- Never create files in data/ unless the task explicitly names them.
- If a task needs data you do not have, stop and say what is missing.
- Never invent sources, licenses, dates or document references.
- At the end of every task, list every file created or changed.
