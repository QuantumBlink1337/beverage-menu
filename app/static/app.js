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

    categories: [
      { id: "all", label: "All" },
      { id: "beer-wine", label: "Beer & Wine" },
      { id: "liquor", label: "Liquor" },
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

    get availableCocktails() {
      return this.hostMode
        ? this.cocktails
        : this.cocktails.filter((c) => c.available);
    },

    get visibleCocktails() {
      const base = this.availableCocktails; // ← getter reading a getter
      switch (this.activeCategory) {
        case "all":
        case "cocktails":
          return base;
        case "non-alcoholic":
          return base.filter((c) =>
            c.tags.some((t) => ["Non-Alcoholic", "Mocktail", "NA"].includes(t)),
          );
        case "thc":
          return base.filter((c) =>
            c.tags.some((t) => ["THC", "Cannabis"].includes(t)),
          );
        default:
          return []; // beverage-only tabs show no cocktails
      }
    },

    get visibleGroups() {
      if (this.activeCategory === "all") return this.beverages;
      const tabToGroups = {
        "beer-wine": ["Beer", "Wine"],
        liquor: ["Liquor"],
        "coffee-tea": ["Coffee", "Tea"],
      };
      const wanted = tabToGroups[this.activeCategory];
      if (!wanted) return []; // cocktail-only tabs show no beverages
      return this.beverages.filter((g) => wanted.includes(g.name));
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
  };
}
