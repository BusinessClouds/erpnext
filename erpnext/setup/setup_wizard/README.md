# Setup wizard chart selection

The organization slide loads country-specific chart options through the Frappe
Select control API. This supports app-customized hidden controls, which have no
DOM input, and keeps the native first-option selection for visible controls.
An older request cannot overwrite a newer country or a rebuilt slide's control.

Run `node --test tests/js/setup_wizard_chart_of_accounts.test.js` for visible,
hidden, empty-result, retry and stale-response cases. This behavior is shared
across SaaS engines; it adds no controller or entitlement behavior.
