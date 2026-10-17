---
name: synthetic-data-generation
description: "Write deterministic seed scripts that fill development, test, demo, or load-test databases with synthetic, referentially intact data that contains no real personal data, with realistic skew and checked integrity. Use when a project needs seed data, fixtures, demo data, or data volume for performance tests. Not for copying or masking production data, and not for load-test scenario design (use the load-testing-suite skill)."
---

# Synthetic Data Generation

Produce seed scripts that generate the same realistic, fully synthetic dataset
on every run, in dependency order, and prove its integrity before claiming it.
The stance is **synthetic only, reproducible, verified**: same seed, same faker
version, and same reference date give the same data, and "integrity verified"
is printed only after the checks run.

## When to use

- Seed data for local development, CI fixtures, or demo environments.
- Data volume for load tests, query-plan checks, or pagination testing.
- Replacing a habit of copying production data into lower environments.

## When not to use

- A request to dump, copy, or sample production data into a lower environment:
  decline and offer the alternatives in Guardrails.
- Designing load-test scenarios and thresholds: use the `load-testing-suite` skill.
- Designing or changing the schema itself: use the `database-design` skill.
- Independent review of the generation design (dependency order, constraints,
  distributions): delegate to the `synthetic-data-architect` subagent.

## Inputs to gather

Discover these before asking. Ask only about what remains ambiguous.

- Schema source: Prisma schema, Drizzle or TypeORM models, SQL migrations, or
  factories. Note foreign keys, unique and check constraints, enums, and
  nullable columns.
- Target database, and how to confirm it is disposable (local container, CI
  service, per-branch database).
- Volumes per table, ratios (orders per user), and distribution needs: skew,
  null rates, date ranges, status mixes.
- Existing seed tooling (for example `npx prisma db seed`, fixture loaders,
  factory_boy) and the installed faker library and exact version.

## Workflow

1. **Confirm the target is disposable.** Read the configured connection target
   and show only the host and database name, never credentials. If it is not
   obviously local or CI, ask. Never seed a shared or production database.
2. **Order tables by dependency.** Topologically sort the foreign-key graph so
   parents load before children. For cycles (a self-referencing `manager_id`,
   or two tables that reference each other), insert with the foreign key null
   and fill it in a second pass, or use deferrable constraints.
3. **Make it deterministic.**
   - Call `faker.seed(N)` once, before any generation.
   - Call `faker.setDefaultRefDate(fixedDate)`: `faker.date.past()` and
     `faker.date.recent()` are relative to the current time otherwise.
   - Pin the exact faker version (no `^` range); the same seed can produce
     different values across versions.
   - Use no other randomness or clock (`Math.random`, `Date.now`,
     `crypto.randomUUID`, database defaults such as `now()` or generated ids):
     set ids and timestamps explicitly. Generate in a fixed order.
4. **Derive unique values from the row index** (`user42@example.test`) instead
   of retrying random draws; random values collide at volume.
5. **Model distributions.** Skew parent selection with a Zipf sampler (below),
   weight enum values, apply explicit null rates, and keep dates consistent
   (an order never predates its user).
6. **Keep everything obviously fake.** Emails on RFC 2606 reserved names
   (`example.com`, `.test`); IPv4 from the RFC 5737 documentation ranges
   (`192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`) and IPv6 from
   `2001:db8::/32`; phone numbers in the fictional 555-0100 to 555-0199 range;
   card numbers only from the payment provider's published test numbers. Never
   generate random Luhn-valid card numbers: they can be real cards.
7. **Insert in batches** with `createMany`, multi-row `INSERT`, or `COPY` for
   large volumes. Keep rows times columns per statement under the driver's
   bind-parameter limit (PostgreSQL allows at most 65,535 parameters per
   statement); for example 1,000 to 5,000 rows per batch.
8. **Verify, then report.** Check row counts per table, run an orphan check per
   foreign key, and check uniqueness and the intended skew. Orphan checks matter
   most where the database does not enforce foreign keys (for example Prisma
   `relationMode = "prisma"`, MongoDB, or constraints dropped for load speed).
9. **Make reruns safe.** Prefer seeding a fresh database created for this run.
   Resetting an existing one destroys its data: do it only with approval and a
   confirmed disposable target.

## Reference example: Prisma seed script

Illustrative TypeScript against the `@faker-js/faker` v8+ API and a Prisma
schema with `User` and `Order` models. Run it through the project's seed
command (for example `npx prisma db seed`).

```typescript
import { PrismaClient } from '@prisma/client';
import { faker } from '@faker-js/faker';

const prisma = new PrismaClient();
const SEED = 42;
const REF_DATE = new Date('2026-01-01T00:00:00.000Z');
const BATCH_SIZE = 2000;
const USER_COUNT = 5000;
const ORDER_COUNT = 25000;

faker.seed(SEED);
faker.setDefaultRefDate(REF_DATE); // date.past() and friends are relative to this, not now

// Rank k (1-based) is drawn with probability proportional to 1 / k^s. Build the
// cumulative weights once, then binary-search a seeded uniform draw.
function makeZipfSampler<T>(items: T[], s = 1.2): () => T {
  if (items.length === 0) throw new Error('cannot sample from an empty pool');
  const cdf: number[] = [];
  let total = 0;
  for (let k = 1; k <= items.length; k++) {
    total += 1 / Math.pow(k, s);
    cdf.push(total);
  }
  return () => {
    const target = faker.number.float({ min: 0, max: 1 }) * total;
    let lo = 0;
    let hi = items.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (cdf[mid] > target) hi = mid;
      else lo = mid + 1;
    }
    return items[lo];
  };
}

interface SeededUser { id: string; createdAt: Date }

async function seedUsers(): Promise<SeededUser[]> {
  const users: SeededUser[] = [];
  for (let start = 0; start < USER_COUNT; start += BATCH_SIZE) {
    const size = Math.min(BATCH_SIZE, USER_COUNT - start);
    const data = Array.from({ length: size }, (_, j) => {
      const user = { id: faker.string.uuid(), createdAt: faker.date.past({ years: 2 }) };
      users.push(user);
      return {
        ...user,
        email: `user${start + j}@example.test`, // unique by index; RFC 2606 reserved TLD
        fullName: faker.person.fullName(),
      };
    });
    await prisma.user.createMany({ data });
  }
  return users;
}

async function seedOrders(users: SeededUser[]): Promise<void> {
  // Shuffle first so the heavy users are not simply the earliest created.
  const pickUser = makeZipfSampler(faker.helpers.shuffle(users));
  for (let start = 0; start < ORDER_COUNT; start += BATCH_SIZE) {
    const size = Math.min(BATCH_SIZE, ORDER_COUNT - start);
    const data = Array.from({ length: size }, () => {
      const user = pickUser();
      return {
        id: faker.string.uuid(),
        userId: user.id,
        amountCents: faker.number.int({ min: 500, max: 50_000 }),
        status: faker.helpers.weightedArrayElement([
          { weight: 7, value: 'COMPLETED' },
          { weight: 2, value: 'PENDING' },
          { weight: 1, value: 'CANCELLED' },
        ]),
        createdAt: faker.date.between({ from: user.createdAt, to: REF_DATE }), // never before its user
      };
    });
    await prisma.order.createMany({ data });
  }
}

// Claim integrity only after checking it. Table and column names depend on the
// Prisma schema's mapping.
async function verify(): Promise<void> {
  const users = await prisma.user.count();
  const orders = await prisma.order.count();
  if (users !== USER_COUNT || orders !== ORDER_COUNT) {
    throw new Error(`row counts: users ${users}/${USER_COUNT}, orders ${orders}/${ORDER_COUNT}`);
  }
  const [{ orphans }] = await prisma.$queryRaw<{ orphans: bigint }[]>`
    SELECT count(*) AS orphans
    FROM "Order" o LEFT JOIN "User" u ON u.id = o."userId"
    WHERE u.id IS NULL`;
  if (Number(orphans) !== 0) throw new Error(`${orphans} orders reference missing users`);
}

async function main(): Promise<void> {
  const users = await seedUsers();
  await seedOrders(users);
  await verify();
  console.log(`Seeded ${USER_COUNT} users and ${ORDER_COUNT} orders; row counts and orphan check passed.`);
}

main()
  .catch((err) => {
    console.error('Seed failed:', err);
    process.exitCode = 1;
  })
  .finally(() => prisma.$disconnect());
```

The row-count check assumes the tables were empty before seeding. If a rerun
needs a clean slate, resetting with Prisma drops all data in the target
database, so it runs only after the user approves and the target is confirmed
disposable:

```bash
npx prisma migrate reset --force  # requires approval: deletes all data in the target database
```

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions,
  including any reset, truncate, or drop of an existing database.
- Never weaken a test, check, or threshold to make work pass.
- Never dump, copy, or sample production data into this workflow. Real
  personal data in development or CI widens who can see it, usually exceeds
  the purpose it was collected for, and lands on machines with weaker
  controls. Say so plainly and offer alternatives: a schema-only dump (for
  example `pg_dump --schema-only`), synthetic data shaped by aggregate
  statistics the data owner approves (row counts, null rates, value
  distributions), or an anonymization pipeline that the data owner has approved
  and runs.
- Never print or log connection strings or credentials.
- Do not claim integrity, determinism, or distribution fit without the check
  that shows it.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- The seed command exits zero on a fresh disposable database, and its own
  row-count and orphan checks pass.
- Determinism: two runs into two fresh databases produce identical content, for
  example the same result from
  `SELECT md5(string_agg(id || ':' || email || ':' || "createdAt", ',' ORDER BY id)) FROM "User";`
- Skew: a group-by on the child foreign key shows the intended heavy tail (a
  few parents own a large share of children).
- No real-looking personal data: emails, IPs, and phone numbers fall inside the
  reserved ranges.
- The project's type check and tests pass with the seeded data.

## Report

- **Target:** database and how it was confirmed disposable.
- **Order:** tables in dependency order, and how cycles were handled.
- **Volumes and distributions:** rows per table, skew parameters, null rates.
- **Determinism:** seed, reference date, pinned faker version, and the
  repeat-run comparison result.
- **Integrity:** row counts, orphan checks, and uniqueness results.
- **Not verified:** checks that could not run and why.

## Optional delegation

The `synthetic-data-architect` subagent can review the schema for dependency
order, constraints, and realistic distributions before you write the
generator; verify its findings against the schema. One agent can complete this
workflow alone.
