// Rules shared by the two TypeScript packages; the parser comes from each lockfile.
module.exports = function configuration(parser) {
  const rules = {
    "no-debugger": "error",
    "no-dupe-else-if": "error",
    "no-duplicate-case": "error",
    "no-unreachable": "error",
    "use-isnan": "error",
    "valid-typeof": "error",
    eqeqeq: ["error", "always", { null: "ignore" }],
  };
  return [
    { ignores: ["**/node_modules/**", "dist/**", "dist-test/**"] },
    {
      files: ["**/*.ts"],
      languageOptions: {
        parser,
        parserOptions: { ecmaVersion: 2022, sourceType: "module" },
      },
      rules,
    },
    {
      files: ["**/*.js", "**/*.cjs"],
      languageOptions: { ecmaVersion: 2022, sourceType: "commonjs" },
      rules,
    },
  ];
};
