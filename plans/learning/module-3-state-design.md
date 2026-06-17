# Module 3 — State Design (Cheat Sheet)

> Earned knowledge from the frontend architecture quiz. What lives in the `app()`
> state object, why, and the principles that decide its shape. Anchored to Angular.

---

## 1. What "state" actually is

**State is what *varies*. Unchanging structure is just template/HTML.**

The test for "does this belong in state?":
> Could it be different from one **moment** to the next, or one **viewer** to the next?

- Navbar / logo → always identical → **not state**, just markup (you'd never put `<nav>` in an Angular component *field*).
- The drink data, the selected tab, what's expanded, guest-vs-host → vary → **state**.
- Pixel/scroll positions → the browser's job (DOM/CSS), **not app state**.

---

## 2. `app()` is your component class, written as a function

Alpine has no classes. A component = **a function that returns a plain object**. That
object holds **both state (properties) and behavior (methods)** — exactly like an Angular
component class holds fields + methods, and the template binds to both.

```js
function app() {
  return {
    activeCategory: 'all',        // property → state (like a component field)
    toggleCard(id) { /* … */ },   // method   → behavior (like a component method)
  }
}
```
```html
<body x-data="app()">
  <button @click="toggleCard(c.id)" x-text="activeCategory"></button>
</body>
```

- `x-data="app()"` → Alpine calls `app()` **once**, wraps the returned object in the
  reactive **Proxy** (Module 1), and that object becomes the scope for everything inside.
- **In the HTML you don't write `this`** — `x-text="activeCategory"`, not `this.activeCategory`.
  The object *is* the scope (like `{{ activeCategory }}` in an Angular template).
- **Inside a method you *do* use `this`** — `this.expandedIds` — same as `this` in an Angular method.
- Define `app()` in `app.js`, loaded **before** Alpine, so it exists when `x-data` evaluates.

---

## 3. Categories of state (a lens for any field)

| Category | Examples here | Notes |
|---|---|---|
| **Server data** | `beverages`, `cocktails` | Fetched, not authored in the browser. Keep it **pure** — don't bolt UI flags onto it. |
| **Async lifecycle** | `status` | Tracks where the fetch is: loading / ready / error. |
| **UI state** | `activeCategory`, `expandedCocktailIds` | What the user is doing right now. |
| **Mode** | `hostMode` | Read once from the URL; varies per *viewer*, not moment-to-moment. |
| **Host-only data** | `mappings` | Declared always; **stays empty/unused** for guests. Host-only doesn't change the *structure*. |

---

## 4. The principles that decide a field's shape

**a. Single source of truth.** A fact lives in exactly *one* place. Storing "is this card
open?" as both a per-card flag *and* a global variable = two places that can disagree = bug.

**b. Make illegal states unrepresentable.** Choose a representation whose possible values
map onto your *legal* states — so bad states can't even be expressed.
- "At most one card open" → a single `expandedId` (two-open is structurally impossible)
  beats a boolean-per-card (nothing stops two `true`s).
- Loading vs error → a single `status` enum (`'loading'|'ready'|'error'`) beats two booleans
  `loading`+`error` (which allow the nonsense `loading && error`).
- This is the same instinct as reaching for a C# `enum` over three loose `bool`s.

**c. Match the representation to the *legal states*, and re-decide when the rule changes.**
- Single-open accordion → `expandedId` (string|null).
- Multi-open (e.g. host prepping several recipes) → *any subset is legal*, so a collection
  (`Set` / array / object-map) is correct — no illegal states to design out.
- The right shape changed because the *rule* changed, not because the principle did.

**d. Least-privilege default.** `hostMode: false`. Default to the safe/minimal view; require
an explicit signal (`?host=true`) to unlock more. Avoids leaking host-only data to guests.

**e. Declare every field up front** (Module 1 reactivity): properties present when Alpine
wraps the object get tracked by the Proxy. Adding a brand-new key later risks the
"reactivity gotcha" where it isn't tracked. Declare with a safe default now; set the real
value in `init()`.

**f. Sensible initial values.** Empty until loaded (`[]`), nothing-tapped defaults
(`expandedCocktailIds: []`). Don't seed with sample data — that's for testing, not the
initial value.

---

## 5. No class for a cocktail — plain objects from JSON

There is no `CraftedDrink` class in the frontend, and you don't need one. The API returns
JSON → `JSON.parse` → **plain JS objects** (`{ id, name, tags, ingredients, … }`). An object
is just a bag of properties that exists at runtime; nothing declares its shape in advance.

The "shape" lives in:
1. **The server's Pydantic models** (`app/models.py`) — the real contract / your "class".
2. The JSON on the wire.
3. Your head.

This is the dynamic-typing trade-off (Module 1): Angular would give you `interface CraftedDrink`
+ compiler checks; plain JS gives nothing (`cocktails[0].naem` fails silently). Optional escape
hatch with no build step: mirror the model as a **JSDoc `@typedef`** for editor-level checking.

> Java→C analogy: same "everything is an object" → "here's a plain struct" unlearning.

---

## 6. `init()` = `ngOnInit` — where startup work goes

Angular has two startup beats; Alpine mirrors them:

| Angular | Alpine | Purpose |
|---|---|---|
| `constructor` | `app()` being **called** | Build initial state (field defaults). Cheap, synchronous, **no side effects**. |
| `ngOnInit` | **`init()`** (Alpine calls it once, automatically) | **Real startup work**: read the URL, fetch data. |

Rule: **static defaults → the returned object; side-effecting/async startup → `init()`.**
(You can't `await` inside an object literal, which is *why* fetches go in `init()`.)

```js
async init() {
  // 1. who am I? — read mode from the URL FIRST
  this.hostMode = new URLSearchParams(window.location.search).has('host');

  // 2. load public data  (response shapes per models.py)
  this.beverages = (await fetch('/api/beverages').then(r => r.json())).groups;
  this.cocktails = (await fetch('/api/crafted_drinks').then(r => r.json())).crafted_drinks;

  // 3. host-only data — only if host
  if (this.hostMode) {
    this.mappings = (await fetch('/api/mappings').then(r => r.json())).mappings;
  }

  this.status = 'ready';   // (wrap in try/catch → this.status = 'error')
}
```

Because the fields were declared up front, each assignment flows through the Proxy and the
UI fills in reactively as fetches land.

---

## 7. `fetch` & Promises (you already know the cousin)

- `fetch()` returns a **Promise** = "a value that isn't here yet, but will be (or will fail)."
- `.then(cb)` = run on success · `.catch(cb)` = on failure · `.finally(cb)` = either way.
- **Angular anchor:** `HttpClient` returns an RxJS **Observable** you `.subscribe()` to. A Promise
  is basically a one-shot Observable, so **`.then` ≈ `.subscribe`** for a single value.
- `async/await` is **sugar over Promises** — flatter to read; `await` pauses until it resolves.
- **Two-await gotcha:** `fetch` resolves to a `Response` (status/headers, body unread); `res.json()`
  *also* returns a Promise (parsing is async too). So it's always: get response → then parse.

---

## 8. The "empty array" ambiguity → why `status` exists

`cocktails === []` because *still loading* looks identical to `cocktails === []` because
*there genuinely are none* — two different things the UI must say differently. The `status`
field disambiguates:

- `status === 'loading'` → "just a sec…"
- `status === 'ready' && cocktails.length === 0` → "no drinks available"
- `status === 'ready' && cocktails.length > 0` → show the grid
- `status === 'error'` → "couldn't load"

---

## 9. The assembled state object

```js
function app() {
  return {
    // --- server data (empty until fetched) ---
    beverages: [],            // /api/beverages → { groups }
    cocktails: [],            // /api/crafted_drinks → { crafted_drinks }; plain objects, shape = models.py

    // --- async lifecycle ---
    status: 'loading',        // 'loading' | 'ready' | 'error'

    // --- UI state ---
    activeCategory: 'all',
    expandedCocktailIds: [],  // ids (strings) of open cocktail cards; [] = none open

    // --- mode (set from ?host=true in init) ---
    hostMode: false,          // least-privilege default

    // --- host-only data (stays empty for guests) ---
    mappings: [],

    // async init() — Alpine's ngOnInit — reads URL + fetches (see §6)
  }
}
```

> Will grow later: a tag filter / PDF export feature adds a UI field like `selectedTags: []`.
> Add state when a feature earns it, not before.
