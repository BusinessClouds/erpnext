const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function makeField(hidden = false) {
	return {
		df: { hidden, options: [] },
		input: hidden ? undefined : { options: [], value: "" },
		set_options() {
			if (this.input) this.input.options = this.df.options;
		},
		set_value(value) {
			this.value = value;
			if (this.input) this.input.value = value;
		},
	};
}

function loadWizard(hidden, engine) {
	const requests = [];
	const context = {
		__: (value) => value,
		erpnext: { setup: {} },
		frappe: {
			boot: { dafater_saas_engine: engine },
			provide() {},
			pages: { "setup-wizard": {} },
			setup: { on() {} },
			wizard: { values: { country: "Saudi Arabia" } },
			defaults: { get_default: () => "Saudi Arabia" },
			call: (options) => requests.push(options),
		},
	};
	vm.runInNewContext(
		fs.readFileSync(path.resolve(__dirname, "../../erpnext/public/js/setup_wizard.js"), "utf8"),
		context
	);
	const slide = context.erpnext.setup.slides_settings.find((item) => item.name === "organization");
	slide.field = makeField(hidden);
	slide.get_field = (name) => (name === "chart_of_accounts" ? slide.field : undefined);
	slide.get_input = () => assert.fail("The loader must support controls without DOM inputs");
	return { slide, requests, frappe: context.frappe, load: () => slide.load_chart_of_accounts(slide) };
}

for (const engine of [undefined, "legacy_v2", "press"]) {
	for (const hidden of [false, true]) {
		test(`${engine || "unconfigured"} ${
			hidden ? "hidden" : "visible"
		} chart selects the first country option`, () => {
			const { slide, requests, load } = loadWizard(hidden, engine);
			load();
			assert.equal(requests.length, 1);
			assert.equal(
				requests[0].method,
				"erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts.get_charts_for_country"
			);
			assert.equal(requests[0].args.country, "Saudi Arabia");
			assert.equal(requests[0].args.with_standard, true);
			requests[0].callback({ message: ["Saudi Chart", "Standard"] });
			assert.deepEqual(slide.field.df.options, ["Saudi Chart", "Standard"]);
			assert.equal(slide.field.value, "Saudi Chart");
			if (!hidden) assert.equal(slide.field.input.value, "Saudi Chart");
		});
	}
}

test("a new country response wins even when the older response arrives last", () => {
	const { slide, requests, load, frappe } = loadWizard(true);
	load();
	frappe.wizard.values.country = "Egypt";
	load();
	requests[1].callback({ message: ["Egypt Chart"] });
	requests[0].callback({ message: ["Saudi Chart"] });
	assert.equal(slide.field.value, "Egypt Chart");
});

test("responses cannot update a rebuilt control or a country changed without another request", () => {
	const { slide, requests, load, frappe } = loadWizard(true);
	load();
	const original = slide.field;
	slide.field = makeField(true);
	requests[0].callback({ message: ["Saudi Chart"] });
	assert.equal(original.value, undefined);
	assert.equal(slide.field.value, undefined);
	load();
	frappe.wizard.values.country = "Egypt";
	requests[1].callback({ message: ["Saudi Chart"] });
	assert.equal(slide.field.value, undefined);
});

test("a missing control issues no lookup and empty results clear an earlier selection", () => {
	const { slide, requests, load } = loadWizard(true);
	slide.field = null;
	load();
	assert.equal(requests.length, 0);
	slide.field = makeField(true);
	slide.field.value = "Old Chart";
	load();
	requests[0].callback({ message: [] });
	assert.equal(slide.field.value, "");
	assert.deepEqual(slide.field.df.options, []);
});

test("a failed lookup can be retried and malformed responses do not change the control", () => {
	const { slide, requests, load } = loadWizard(true);
	slide.field.value = "Saved Chart";
	load();
	requests[0].callback({});
	assert.equal(slide.field.value, "Saved Chart");
	load();
	requests[1].callback({ message: ["Current Chart"] });
	assert.equal(slide.field.value, "Current Chart");
});
