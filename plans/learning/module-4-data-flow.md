# Module 4 — Data Flow (Cheat Sheet)

> Getting data into the app and handling the async reality. Anchored to Angular/RxJS.
> Implemented in `app/static/app.js` (`init()` + the fetches).

---

## 1. Fetch-everything-up-front vs fetch-per-view

**Approach A — fetch all once, filter in the browser** (what this project does).
**Approach B — fetch per tab/view** (the typical enterprise-Angular default).

**A wins here because:**
- **Instant tab switching.** Data's already in memory → filtering is zero-network, no spinner.
  B pays a network round-trip *every tap* — a repeated tax, painful on cellular.
- **Resilience.** Once loaded, every tab works even if the connection drops.
- **Zero backend changes.** The handoff says *"all filtering is client-side"* — the category
  tabs are a frontend concept (Grocy groups + Notion tags); there are no per-tab endpoints.
- **Fewer requests** (2 total) — kinder to the QR-code-five-guests scenario.

**B wins when the dataset is too big / too fresh / too sliced / too sensitive to ship wholesale:**
- too big (thousands of rows), too fresh (live prices/inventory), too sliced (pagination/
  infinite scroll), too sensitive (server gates per request).

Your work apps lean B because they're usually "too big / too fresh / too sliced." This menu is
none of those. **Same match-to-scale judgment as Alpine-vs-Angular, applied to data volume.**

> Through-line: choosing A turns a *data-fetching* problem into a *data-filtering* problem →
> sets up Module 5 (derived state). "Static document, lightly enhanced," applied to data.

---

## 2. Concurrent fetches — `Promise.all`

**The trap (sequential awaits serialize independent work):**
```js
this.beverages = await fetch('/api/beverages')...      // 0→400ms
this.cocktails = await fetch('/api/crafted_drinks')... // 400→800ms (only starts now!)
```
≈ 800ms, because the 2nd request doesn't *leave* until the 1st returns — a dependency that
doesn't exist in the data.

**Key mental model: a fetch starts when you *call* it, not when you *await* it.** `fetch()`
kicks off the request immediately and returns a Promise (a handle to work already in flight).
So: start both first, then await both.

```js
const [bev, cocktails] = await Promise.all([
  fetch('/api/beverages').then(r => r.json()),
  fetch('/api/crafted_drinks').then(r => r.json()),
]);
```
Both fly at once → ≈ 400ms. `Promise.all` takes many promises, returns **ONE** aggregate
promise that resolves to the array of results.

**"Parallel" on a single-threaded language:** it's concurrent *I/O*, not CPU threads. The
network happens *outside* the JS thread; JS fires both off and waits for callbacks. The
*requests* overlap in wall-clock time; your code never runs two lines at once. (Same reason
Node scales on one thread — it's waiting, not computing.)

**Angular anchor:** `Promise.all` ≈ RxJS `forkJoin([...])`.

---

## 3. Promises & `fetch` (you already know the cousin)

- `fetch()` returns a **Promise** = "a value that isn't here yet, but will be (or will fail)."
- `.then(cb)` success · `.catch(cb)` failure · `.finally(cb)` either way.
- **`.then` ≈ Angular's `.subscribe`** — a Promise is basically a one-shot Observable.
- `async/await` is sugar over Promises; `await` pauses until it resolves.
- **Two-await gotcha:** `fetch` resolves to a `Response` (status/headers, body unread);
  `res.json()` *also* returns a Promise. Always: get response → then parse.

---

## 4. Error handling & partial success — `Promise.allSettled`

`Promise.all` is **fail-fast**: if ANY promise rejects, the whole thing rejects with that error.
Consequence — even successful data is **orphaned**: the rejection makes `await` throw, so the
assignment lines *below* it never run. The good data arrived but never reaches state.

For "show whatever loaded," use **`Promise.allSettled`** — waits for all, reports each outcome
independently, never throws:
```js
const [bev, cocktails] = await Promise.allSettled([...]);
if (bev.status === 'fulfilled')      { this.beverages = bev.value.groups;  this.beverageStatus = 'ready'; }
else                                 { this.beverageStatus = 'error'; }
if (cocktails.status === 'fulfilled'){ this.cocktails  = cocktails.value.crafted_drinks; this.cocktailStatus = 'ready'; }
else                                 { this.cocktailStatus = 'error'; }
```
Each result is `{ status:'fulfilled', value }` or `{ status:'rejected', reason }`.
Rule: **`Promise.all` = all-or-nothing · `Promise.allSettled` = give me each outcome.**

Justified here because cocktails (Notion, cache-backed) is the flakier source; a guest can
still use a beverage list if recipes are down.

---

## 5. The state consequence: status granularity = independent-failure granularity

A single global `status: 'loading'|'ready'|'error'` **can't** describe "beverages loaded,
cocktails failed." Don't enumerate combinations into a flat enum (`partiallyReady`, …) — that's
lossy ("which part?") and explodes as sources multiply.

Instead: **one status field per independently-failing source** (`beverageStatus`, `cocktailStatus`).
"Partial" then isn't a stored state — it's just what the screen looks like when one section
renders and the other shows an error. **Don't store derived combinations; store the atoms.**

> Don't derive readiness from the data array — empty-array is ambiguous (Module 3 §8), which is
> the whole reason `status` is explicit. Derive the *combination*, store the *atoms*.

**Unifying rule:**
- mutually-exclusive facts about *one* unit (loading vs error of one fetch) → collapse to **one enum**.
- things that fail *independently* (beverages vs cocktails) → **one status each**.
Get the granularity right and both illegal states (`loading && error`) and lossy states
("partial-but-which?") disappear.
