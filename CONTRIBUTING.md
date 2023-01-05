# Buzz Contribution Guide

## Internationalization

To contribute a new language translation to Buzz:

1. Run `make translation_po locale=[locale]`. `[locale]` is a string with the format "language\[_script\]\[_country\]",
   where:

    - "language" is a lowercase, two-letter ISO 639 language code,
    - "script" is a titlecase, four-letter, ISO 15924 script code, and
    - "country" is an uppercase, two-letter, ISO 3166 country code.

   For example: `make translation_po locale=en_US`.

2. Fill in the translations in the `.po` file generated in `locale/[locale]/LC_MESSAGES`.
3. Run `make translation_mo` to compile the translations, then test your changes.
4. Create a new pull request with your changes.
