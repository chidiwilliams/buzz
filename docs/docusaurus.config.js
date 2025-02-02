// @ts-check
// Note: type annotations allow type checking and IDEs autocompletion

const lightCodeTheme = require("prism-react-renderer/themes/github");
const darkCodeTheme = require("prism-react-renderer/themes/dracula");

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: "Buzz",
  tagline: "Audio transcription and translation",
  favicon: "img/favicon.ico",

  // Set the production url of your site here
  url: "https://chidiwilliams.github.io",
  // Set the /<baseUrl>/ pathname under which your site is served
  // For GitHub pages deployment, it is often '/<projectName>/'
  baseUrl: "/buzz/",

  // GitHub pages deployment config.
  // If you aren't using GitHub pages, you don't need these.
  organizationName: "chidiwilliams", // Usually your GitHub org/user name.
  projectName: "buzz", // Usually your repo name.

  onBrokenLinks: "throw",
  onBrokenMarkdownLinks: "warn",

  trailingSlash: false,

  // Even if you don't use internalization, you can use this field to set useful
  // metadata like html lang. For example, if your site is Chinese, you may want
  // to replace "en" with "zh-Hans".
  i18n: {
    defaultLocale: "en",
    locales: ["en", "zh"],
    path: "i18n",
    localeConfigs: {
      en: {
        label: "English",
        direction: "ltr",
        htmlLang: "en-US",
        path: "en",
      },
      zh: {
        label: "简体中文",
        direction: "ltr",
        htmlLang: "zh-CN",
        path: "zh",
      },
    },
  },

  presets: [
    [
      "classic",
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          sidebarPath: require.resolve("./sidebars.js"),
        },
        blog: {
          showReadingTime: true,
        },
        theme: {
          customCss: require.resolve("./src/css/custom.css"),
        },
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      // Replace with your project's social card
      image: "img/favicon.ico",
      navbar: {
        title: "Buzz",
        logo: {
          alt: "Buzz",
          src: "img/favicon.ico",
        },
        items: [
          {
            type: "docSidebar",
            sidebarId: "tutorialSidebar",
            position: "left",
            label: "Docs",
          },
          {
            href: "https://github.com/chidiwilliams/buzz",
            label: "GitHub",
            position: "right",
          },
          {
            type: "localeDropdown",
            position: "left",
          },
        ],
      },
      prism: {
        theme: lightCodeTheme,
        darkTheme: darkCodeTheme,
      },
    }),
};

module.exports = config;
