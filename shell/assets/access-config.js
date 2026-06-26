/* Access allowlist — the single source of truth for who may open the dashboard
 * and which views each person sees.
 *
 * LANE-KEEPING ONLY. This gate keeps honest users in their assigned views. It is
 * NOT real security: the dashboard is static files, so anyone who view-sources or
 * fetches projection/dashboard/data/*.js directly can still read the data, and
 * GitHub Pages on a personal account is world-public even for a private repo.
 * See projection/README.md ("Access gates") for the limitations and the upgrade
 * path (edge auth / backend) for the dedicated-service phase.
 *
 * Each entry:
 *   email         approved login (matched case-insensitively).
 *   passwordHash  hex SHA-256 of  email.toLowerCase().trim() + "\n" + password.
 *                 Generate with tools/hash-password.html — never store plaintext.
 *   views         which views this person sees. Valid keys:
 *                   historical       Historical Performance engine
 *                   proj:cohorts     Projection ▸ Thomas · Cohorts
 *                   proj:reps        Projection ▸ Reps
 *                   proj:strategic   Projection ▸ Clanton · Strategic
 *                   proj:management  Projection ▸ Management
 *                   cash             Cash Position engine
 *
 * To add someone: add an entry, generate their hash, save. To revoke: delete the
 * entry. The defaults below are PLACEHOLDERS (password "changeme") — replace the
 * emails and regenerate the hashes before sharing the dashboard with anyone.
 */
window.ACCESS_USERS = [
  // Admin — full access.
  {
    email: "clanton@oceancorp.com",
    passwordHash: "3fee3c45258381a2275e7672518e4955757ba14c4581d27256ecd89577ec3bef",
    views: ["historical", "proj:cohorts", "proj:reps", "proj:strategic", "proj:management", "cash"],
  },
  // Thomas — operational cohort tracking only.
  // NOTE: regenerate this hash for thomas.thomas@oceancorp.com via
  // tools/hash-password.html — the current value was generated for a different
  // email, so login will fail until it is replaced.
  {
    email: "thomas.thomas@oceancorp.com",
    passwordHash: "f91aaf5e9b84a873099572ac8db259d56de4ffa5b4c9fd671dcd1dfe562eca17",
    views: ["historical", "proj:cohorts", "proj:reps", "proj:strategic", "proj:management"],
  },
    {
    email: "afarahmandi@generational.com",
    passwordHash: "386d01a4e2c64a7f1230a03de1efae6148952cffa448d3335724b2c4ce9716e2",
    views: ["historical", "proj:cohorts", "proj:reps", "proj:strategic", "proj:management", "cash"],
  },
      {
    email: "aluft@generational.com",
    passwordHash: "b963012d65d5be8509181d37f1b3765dae1ee43d9259a06ebf2d30614d5faae2",
    views: ["historical", "proj:cohorts", "proj:reps", "proj:strategic", "proj:management", "cash"],
  },
];
