# Changelog

## 2.5.0.5

- Use background task API for scheduled cookie refresh to avoid HA startup blocking warnings
- Add Home Assistant statistics metadata compatibility updates for `mean_type` and `unit_class`
- Centralize release version management with a single `VERSION` source and sync tooling
- Improve docs for installation, cookie retrieval, and script-assisted manual cookie workflows

## 2.5.0.4

- Harden dashboard token extraction for chart context:
  - DOM-based extraction (attribute-order agnostic)
  - Fallback to cookie token when hidden input is absent

## 2.5.0.3

- Version and metadata alignment updates

## 2.5.0.2

- Retry setup automatically when add-on cookie retrieval fails (`ConfigEntryNotReady`)

## 2.5.0.1

- Fix options flow compatibility with newer Home Assistant API behavior
