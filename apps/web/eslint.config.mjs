/**
 * ESLint flat configuration for 知辨 (Zhibian) Web.
 *
 * Uses:
 * - typescript-eslint for TypeScript linting
 * - @next/eslint-plugin-next for Next.js best-practices
 *
 * NOTE: eslint-config-next's bundled eslint-plugin-react is incompatible
 * with eslint v10 (getFilename removed). We use @next/eslint-plugin-next
 * directly instead.
 */

import { defineConfig, globalIgnores } from "eslint/config";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);

// Resolve packages and convert to file:// URLs for ESM compatibility on Windows.
const tsEslintUrl = pathToFileURL(require.resolve("typescript-eslint")).href;
const nextPluginUrl = pathToFileURL(require.resolve("@next/eslint-plugin-next")).href;

const tsEslint = await import(tsEslintUrl);
const nextPlugin = await import(nextPluginUrl);

const eslintConfig = defineConfig([
  // Global ignores.
  globalIgnores([".next/**", "out/**", "build/**", "coverage/**", "next-env.d.ts"]),

  // TypeScript recommended rules.
  ...tsEslint.configs.recommended,

  // Next.js rules.
  {
    plugins: {
      "@next/next": nextPlugin.default ?? nextPlugin,
    },
    rules: {
      "@next/next/google-font-display": "warn",
      "@next/next/google-font-preconnect": "warn",
      "@next/next/inline-script-id": "error",
      "@next/next/next-script-for-ga": "warn",
      "@next/next/no-assign-module-variable": "error",
      "@next/next/no-async-client-component": "error",
      // Removed: rule name not recognized in this version
      "@next/next/no-css-tags": "warn",
      "@next/next/no-document-import-in-page": "error",
      "@next/next/no-duplicate-head": "error",
      "@next/next/no-head-element": "error",
      "@next/next/no-head-import-in-document": "error",
      "@next/next/no-html-link-for-pages": "warn",
      "@next/next/no-img-element": "warn",
      "@next/next/no-page-custom-font": "warn",
      "@next/next/no-script-component-in-head": "error",
      "@next/next/no-styled-jsx-in-document": "error",
      "@next/next/no-sync-scripts": "error",
      "@next/next/no-title-in-document-head": "error",
      "@next/next/no-typos": "error",
      "@next/next/no-unwanted-polyfillio": "warn",
    },
  },

  // Project-specific customizations.
  {
    rules: {
      "@typescript-eslint/no-explicit-any": "warn",
      "import/no-anonymous-default-export": "off",
    },
  },
]);

export default eslintConfig;
