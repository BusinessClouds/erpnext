const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(
	path.join(__dirname, "../../erpnext/accounts/doctype/payment_entry/payment_entry.js"),
	"utf8"
);

function deferred() {
	let resolve, reject;
	const promise = new Promise((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

function setup(doc = {}) {
	const handlers = {};
	const requests = [];
	const failures = [];
	const writes = [];
	const frappe = {
		provide() {},
		ui: { form: { on: (doctype, events) => (handlers[doctype] = events) } },
		call: (options) => {
			requests.push(options);
			return { fail: (callback) => failures.push(callback) };
		},
	};
	vm.runInNewContext(source, {
		frappe,
		cur_frm: { cscript: {} },
		erpnext: { accounts: { taxes: { setup_tax_validations() {}, setup_tax_filters() {} } } },
	});
	const frm = {
		doc: {
			company: "Company A",
			payment_type: "Receive",
			paid_to: "Bank A",
			paid_from: "Party Account",
			...doc,
		},
		set_value: async (field, value) => {
			writes.push([field, value]);
			frm.doc[field] = value;
		},
	};
	const lookup = () => handlers["Payment Entry"].set_company_bank_account(frm);
	return { frm, frappe, requests, failures, writes, lookup, events: handlers["Payment Entry"] };
}

for (const payment_type of ["Pay", "Receive"]) {
	test(`${payment_type} uses the company account and preserves the callback event contract`, async () => {
		const { frm, requests, writes, lookup } = setup({ payment_type });
		assert.equal(lookup(), undefined);
		assert.equal(frm.set_company_bank_account_based_on_coa, true);
		assert.equal(requests[0].method, "frappe.client.get_value");
		assert.equal(requests[0].args.doctype, "Bank Account");
		assert.deepEqual(JSON.parse(JSON.stringify(requests[0].args.filters)), {
			company: "Company A",
			account: payment_type === "Pay" ? "Party Account" : "Bank A",
			disabled: 0,
		});
		await requests[0].callback({ message: { name: "Company Bank" } });
		assert.deepEqual(writes, [["bank_account", "Company Bank"]]);
		assert.equal(frm.set_company_bank_account_based_on_coa, false);
	});
}

test("keeps the recursion guard until bank-account field handlers finish", async () => {
	const { frm, requests, lookup, events } = setup();
	const field_change = deferred();
	frm.set_value = () => {
		assert.equal(frm.set_company_bank_account_based_on_coa, true);
		frm.doc.bank_account = "Company Bank";
		events.bank_account(frm);
		return field_change.promise;
	};
	lookup();
	const callback = requests[0].callback({ message: { name: "Company Bank" } });
	assert.equal(requests.length, 1, "bank-account field handler must not start a recursive lookup");
	assert.equal(frm.set_company_bank_account_based_on_coa, true);
	field_change.resolve();
	await callback;
	assert.equal(frm.set_company_bank_account_based_on_coa, false);
});

test("request failure releases the guard so the user can retry or change bank account", async () => {
	const { frm, requests, lookup, events } = setup();
	lookup();
	requests[0].error({ status: 403 });
	assert.equal(frm.set_company_bank_account_based_on_coa, false);
	frm.doc.bank_account = "Manual Bank";
	events.bank_account(frm);
	assert.equal(
		requests[1].method,
		"erpnext.accounts.doctype.bank_account.bank_account.get_bank_account_details"
	);
	lookup();
	await requests[2].callback({ message: { name: "Retry Bank" } });
	assert.equal(frm.doc.bank_account, "Retry Bank");
	assert.equal(frm.set_company_bank_account_based_on_coa, false);
});

test("an empty result releases the guard without clearing a selected bank", async () => {
	const { frm, requests, writes, lookup } = setup({ bank_account: "Existing Bank" });
	lookup();
	await requests[0].callback({ message: null });
	assert.deepEqual(writes, []);
	assert.equal(frm.doc.bank_account, "Existing Bank");
	assert.equal(frm.set_company_bank_account_based_on_coa, false);
});

test("transport rejection releases the guard even if Frappe skips the error callback", () => {
	const { frm, failures, lookup } = setup();
	lookup();
	failures[0]({ status: 403 });
	assert.equal(frm.set_company_bank_account_based_on_coa, false);
	lookup();
	failures[0]({ status: 403 });
	assert.equal(frm.set_company_bank_account_based_on_coa, true);
	failures[1]({ status: 504 });
	assert.equal(frm.set_company_bank_account_based_on_coa, false);
});

test("field-handler rejection releases the guard and stays rejected", async () => {
	const { frm, requests, lookup } = setup();
	const failure = new Error("field handler failed");
	frm.set_value = async () => {
		throw failure;
	};
	lookup();
	await assert.rejects(requests[0].callback({ message: { name: "Company Bank" } }), failure);
	assert.equal(frm.set_company_bank_account_based_on_coa, false);
});

test("synchronous request failure releases the guard and stays thrown", () => {
	const { frm, frappe, lookup } = setup();
	const failure = new Error("request setup failed");
	frappe.call = () => {
		throw failure;
	};
	assert.throws(lookup, failure);
	assert.equal(frm.set_company_bank_account_based_on_coa, false);
});

test("an older success or failure cannot write or release the newer request guard", async () => {
	const { frm, requests, writes, lookup } = setup();
	lookup();
	frm.doc.paid_to = "Bank B";
	lookup();
	await requests[0].callback({ message: { name: "Stale Bank" } });
	requests[0].error({ status: 403 });
	assert.deepEqual(writes, []);
	assert.equal(frm.set_company_bank_account_based_on_coa, true);
	await requests[1].callback({ message: { name: "Current Bank" } });
	assert.equal(frm.doc.bank_account, "Current Bank");
	assert.equal(frm.set_company_bank_account_based_on_coa, false);
});

test("same-input retries still supersede older requests", async () => {
	const { frm, requests, writes, lookup } = setup();
	lookup();
	lookup();
	await requests[1].callback({ message: { name: "Current Bank" } });
	await requests[0].callback({ message: { name: "Stale Bank" } });
	assert.deepEqual(writes, [["bank_account", "Current Bank"]]);
	assert.equal(frm.set_company_bank_account_based_on_coa, false);
});

test("a finishing field-handler promise cannot release a newer lookup guard", async () => {
	const { frm, requests, lookup } = setup();
	const field_change = deferred();
	frm.set_value = () => field_change.promise;
	lookup();
	const old_callback = requests[0].callback({ message: { name: "Bank A" } });
	frm.doc.paid_to = "Bank B";
	lookup();
	field_change.resolve();
	await old_callback;
	assert.equal(frm.set_company_bank_account_based_on_coa, true);
	await requests[1].callback({ message: null });
	assert.equal(frm.set_company_bank_account_based_on_coa, false);
});

test("an older field-handler rejection preserves a newer lookup guard", async () => {
	const { frm, requests, lookup } = setup();
	const field_change = deferred();
	frm.set_value = () => field_change.promise;
	lookup();
	const old_callback = requests[0].callback({ message: { name: "Bank A" } });
	frm.doc.paid_to = "Bank B";
	lookup();
	const failure = new Error("old field handler failed");
	field_change.reject(failure);
	await assert.rejects(old_callback, failure);
	assert.equal(frm.set_company_bank_account_based_on_coa, true);
	await requests[1].callback({ message: null });
	assert.equal(frm.set_company_bank_account_based_on_coa, false);
});

for (const [label, change] of [
	["company", (frm) => (frm.doc.company = "Company B")],
	["payment direction", (frm) => (frm.doc.payment_type = "Pay")],
	["company account", (frm) => (frm.doc.paid_to = "Bank B")],
	["document", (frm) => (frm.doc = { ...frm.doc })],
]) {
	test(`changed ${label} rejects a response even before another lookup starts`, async () => {
		const { frm, requests, writes, lookup } = setup();
		lookup();
		change(frm);
		await requests[0].callback({ message: { name: "Stale Bank" } });
		assert.deepEqual(writes, []);
		assert.equal(frm.set_company_bank_account_based_on_coa, false);
	});
}

for (const [label, change] of [
	["missing company", (frm) => (frm.doc.company = "")],
	["missing account", (frm) => (frm.doc.paid_to = "")],
	["Internal Transfer", (frm) => (frm.doc.payment_type = "Internal Transfer")],
]) {
	test(`${label} cancels the pending lookup without making another request`, async () => {
		const { frm, requests, writes, lookup } = setup();
		lookup();
		change(frm);
		lookup();
		assert.equal(requests.length, 1);
		assert.equal(frm.set_company_bank_account_based_on_coa, false);
		await requests[0].callback({ message: { name: "Stale Bank" } });
		assert.deepEqual(writes, []);
		assert.equal(frm.set_company_bank_account_based_on_coa, false);
	});
}
