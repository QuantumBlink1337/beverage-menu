// ---------------------------------------------------------------------------
// Static config
// ---------------------------------------------------------------------------

// Which display tab(s) each Grocy product group appears under.
// (Keys must match the Grocy group names exactly.)
const GROUP_TABS = {
  Beer: ["beer-wine"],
  Wine: ["beer-wine"],
  Bourbon: ["liquor"],
  Vodka: ["liquor"],
  Gin: ["liquor"],
  Rum: ["liquor"],
  Liqueors: ["liquor"],
  NA: ["liquor", "non-alcoholic"], // browsable on Bar Stock AND Non-Alcoholic
  Soda: ["non-alcoholic"],
  Coffee: ["coffee-tea", "non-alcoholic"],
  Tea: ["coffee-tea", "non-alcoholic"],
  THC: ["thc"], // finished THC drinks — featured + THC tab
  THCMixer: ["thc", "liquor"], // THC spirit — THC tab + Bar Stock, hidden from Featured
  Mixers: ["liquor"],
};

// Groups kept off the "Featured" overview (deep-cut / ingredient bottles),
// still browsable on their own tab.
const DRILLDOWN_ONLY = new Set(["Liqueors", "NA", "THCMixer", "Mixers"]);

// Notion multi-select option colors → palette-harmonized pill colors.
const TAG_COLORS = {
  default: { bg: "#e9e2cc", fg: "#4e220f" },
  gray: { bg: "#d9d6cb", fg: "#4e220f" },
  brown: { bg: "#9d6638", fg: "#f7f1de" },
  orange: { bg: "#d98a3d", fg: "#3a1c0c" },
  yellow: { bg: "#e3c766", fg: "#3a2c0c" },
  green: { bg: "#b0ba99", fg: "#34401f" },
  blue: { bg: "#8fa9b0", fg: "#1f3640" },
  purple: { bg: "#a892b0", fg: "#2f1f40" },
  pink: { bg: "#c79aa6", fg: "#40202b" },
  red: { bg: "#9c3a23", fg: "#f7f1de" },
};

function app() {
  return {
    // --- server data (empty until fetched) ---
    beverages: [], // /api/beverages → { groups }
    cocktails: [], // /api/crafted_drinks → { crafted_drinks }

    beverageStatus: "loading", // 'loading' | 'ready' | 'error'
    cocktailStatus: "loading",

    // --- UI state ---
    activeCategory: "all",
    expandedCocktailIds: [], // ids of open cocktail cards (multi-open)

    hostMode: false,
    mappings: [],

    // host "Refresh data" button
    refreshing: false,
    refreshMessage: "",

    categories: [
      { id: "all", label: "Featured" },
      { id: "beer-wine", label: "Beer & Wine" },
      { id: "liquor", label: "Bar Stock" },
      { id: "cocktails", label: "Cocktails" },
      { id: "coffee-tea", label: "Coffee & Tea" },
      { id: "non-alcoholic", label: "Non-Alcoholic" },
      { id: "thc", label: "THC" },
    ],

    async init() {
      this.hostMode = new URLSearchParams(location.search).has("host");

      const [bev, cocktails] = await Promise.allSettled([
        fetch("/api/beverages").then((r) => r.json()),
        fetch("/api/crafted_drinks").then((r) => r.json()),
      ]);

      if (bev.status === "fulfilled") {
        this.beverages = bev.value.groups;
        this.beverageStatus = "ready";
      } else {
        this.beverageStatus = "error";
      }

      if (cocktails.status === "fulfilled") {
        this.cocktails = cocktails.value.crafted_drinks;
        this.cocktailStatus = "ready";
      } else {
        this.cocktailStatus = "error";
      }

      if (this.hostMode) {
        try {
          const m = await fetch("/api/mappings").then((r) => r.json());
          this.mappings = m.mappings;
        } catch (e) {
          /* host-only convenience; ignore failures */
        }
      }
    },

    // --- derived: cocktails ---
    get availableCocktails() {
      return this.hostMode
        ? this.cocktails
        : this.cocktails.filter((c) => c.available);
    },

    get visibleCocktails() {
      const base = this.availableCocktails; // ← getter reading a getter
      switch (this.activeCategory) {
        case "all": // Featured → only cocktails tagged "Featured"
          return base.filter((c) => c.tags.some((t) => t.name === "Featured"));
        case "cocktails": // the full cocktail list
          return base;
        case "non-alcoholic":
          return base.filter((c) =>
            c.tags.some((t) =>
              ["Non-Alcoholic", "Mocktail", "NA"].includes(t.name),
            ),
          );
        case "thc":
          return base.filter((c) =>
            c.tags.some((t) => ["THC", "Cannabis"].includes(t.name)),
          );
        default:
          return []; // beverage-only tabs show no cocktails
      }
    },

    // --- derived: beverages ---
    // A group shows on the Bar Stock (liquor) tab.
    onBarStock(name) {
      return (GROUP_TABS[name] || []).includes("liquor");
    },

    get visibleGroups() {
      // Bar Stock → the full inventory, every liquor group broken out
      if (this.activeCategory === "liquor") {
        return this.beverages.filter((g) => this.onBarStock(g.name));
      }
      // Featured → curated: drill-down groups hidden, real spirits collapsed
      if (this.activeCategory === "all") {
        const shown = this.beverages.filter((g) => !DRILLDOWN_ONLY.has(g.name));
        const groups = shown.filter((g) => !this.onBarStock(g.name));
        const spirits = shown.filter((g) => this.onBarStock(g.name));
        if (spirits.length) {
          groups.push({
            name: "Spirits",
            products: spirits.flatMap((g) => g.products),
          });
        }
        return groups;
      }
      // every other tab → straight mapping
      return this.beverages.filter((g) =>
        (GROUP_TABS[g.name] || []).includes(this.activeCategory),
      );
    },

    // --- methods ---
    selectCategory(id) {
      this.activeCategory = id;
    },

    toggleCocktail(id) {
      const i = this.expandedCocktailIds.indexOf(id);
      if (i === -1)
        this.expandedCocktailIds.push(id); // open
      else this.expandedCocktailIds.splice(i, 1); // close
    },

    isExpanded(id) {
      return this.expandedCocktailIds.includes(id);
    },

    ingredientNames(c) {
      const names = c.ingredients.map((i) => i.ingredient);
      if (names.length <= 1) return names.join("");
      return names.slice(0, -1).join(", ") + " and " + names[names.length - 1];
    },

    // Notion option color → inline pill style.
    tagStyle(tag) {
      const c = TAG_COLORS[tag.color] || TAG_COLORS.default;
      return `background:${c.bg}; color:${c.fg}`;
    },

    // Host: force a Grocy + Notion cache refresh (both run server-side, in the background).
    async refreshData() {
      this.refreshing = true;
      this.refreshMessage = "";
      try {
        await Promise.allSettled([
          fetch("/api/beverages/refresh", { method: "POST" }),
          fetch("/api/crafted_drinks/refresh", { method: "POST" }),
        ]);
        this.refreshMessage =
          "Refreshing in the background — reload in a moment.";
      } finally {
        this.refreshing = false;
      }
    },
  };
}
