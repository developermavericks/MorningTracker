# Project-Scoped Rules & Guidelines

Whenever making any updates or introducing new changes to this project, you must adhere to the following rules:

1. **Keep the Change & Deployment Log Updated:**
   * For every feature, bugfix, or schema update implemented, you MUST append a chronological log entry to [DEVELOPMENT_HISTORY.md](file:///e:/MAVERICKS/zMorning_Tracker_Synced_Git/DEVELOPMENT_HISTORY.md).
   * Specify the exact timestamp (IST), git commit hash (if pushed), author, feature scope, and deployment status.
   * If a major database migration, backend task, or api schema changes, add details to the architectural phase sections.

2. **Maintain the Diagnostics Script:**
   * If database models are extended, or new API credentials/integrations are introduced, update the diagnostic validation script [diagnose_takeaways_scheduler.py](file:///e:/MAVERICKS/zMorning_Tracker_Synced_Git/backend/scripts/diagnose_takeaways_scheduler.py) to check the health of the new configurations.

3. **Keep the Rollback Script Valid:**
   * Ensure that rollback recipes (e.g. [rollback_monthly_takeaways.ps1](file:///e:/MAVERICKS/zMorning_Tracker_Synced_Git/backend/scripts/rollback_monthly_takeaways.ps1)) are updated or new rollback recipes are created to allow safe, fast recovery to the last stable state in case of deployment failures.
