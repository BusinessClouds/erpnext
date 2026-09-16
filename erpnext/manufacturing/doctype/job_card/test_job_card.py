# Copyright (c) 2021, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt


from typing import Literal

import frappe
from frappe.test_runner import make_test_records
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import flt, random_string
from frappe.utils.data import add_to_date, now, today

from erpnext.manufacturing.doctype.job_card.job_card import (
	JobCardOverTransferError,
	OperationMismatchError,
	OverlapError,
	make_corrective_job_card,
	make_material_request,
)
from erpnext.manufacturing.doctype.job_card.job_card import (
	make_stock_entry as make_stock_entry_from_jc,
)
from erpnext.manufacturing.doctype.work_order.test_work_order import make_wo_order_test_record
from erpnext.manufacturing.doctype.work_order.work_order import WorkOrder
from erpnext.manufacturing.doctype.workstation.test_workstation import make_workstation
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry


class TestJobCard(FrappeTestCase):
	def setUp(self):
		make_bom_for_jc_tests()
		self.transfer_material_against: Literal["Work Order", "Job Card"] = "Work Order"
		self.source_warehouse = None
		self._work_order = None

	@property
	def work_order(self) -> WorkOrder:
		"""Work Order lazily created for tests."""
		if not self._work_order:
			self._work_order = make_wo_order_test_record(
				item="_Test FG Item 2",
				qty=2,
				transfer_material_against=self.transfer_material_against,
				source_warehouse=self.source_warehouse,
			)
		return self._work_order

	def generate_required_stock(self, work_order: WorkOrder) -> None:
		"""Create twice the stock for all required items in work order."""
		for item in work_order.required_items:
			make_stock_entry(
				item_code=item.item_code,
				target=item.source_warehouse or self.source_warehouse,
				qty=item.required_qty * 2,
				basic_rate=100,
			)

	def tearDown(self):
		frappe.db.rollback()

	def test_job_card_operations(self):
		job_cards = frappe.get_all(
			"Job Card", filters={"work_order": self.work_order.name}, fields=["operation_id", "name"]
		)

		if job_cards:
			job_card = job_cards[0]
			frappe.db.set_value("Job Card", job_card.name, "operation_row_number", job_card.operation_id)

			doc = frappe.get_doc("Job Card", job_card.name)
			doc.operation_id = "Test Data"
			self.assertRaises(OperationMismatchError, doc.save)

	def test_job_card_with_different_work_station(self):
		job_cards = frappe.get_all(
			"Job Card",
			filters={"work_order": self.work_order.name},
			fields=["operation_id", "workstation", "name", "for_quantity"],
		)

		job_card = job_cards[0]

		if job_card:
			workstation = frappe.db.get_value(
				"Workstation", {"name": ("not in", [job_card.workstation])}, "name"
			)

			if not workstation or job_card.workstation == workstation:
				workstation = make_workstation(workstation_name=random_string(5)).name

			doc = frappe.get_doc("Job Card", job_card.name)
			doc.workstation = workstation
			doc.append(
				"time_logs",
				{
					"from_time": "2009-01-01 12:06:25",
					"to_time": "2009-01-01 12:37:25",
					"time_in_mins": "31.00002",
					"completed_qty": job_card.for_quantity,
				},
			)
			doc.submit()

			completed_qty = frappe.db.get_value(
				"Work Order Operation", job_card.operation_id, "completed_qty"
			)
			self.assertEqual(completed_qty, job_card.for_quantity)

	def test_job_card_overlap(self):
		wo2 = make_wo_order_test_record(item="_Test FG Item 2", qty=2)

		jc1 = frappe.get_last_doc("Job Card", {"work_order": self.work_order.name})
		jc2 = frappe.get_last_doc("Job Card", {"work_order": wo2.name})

		employee = "_T-Employee-00001"  # from test records

		jc1.append(
			"time_logs",
			{
				"from_time": "2021-01-01 00:00:00",
				"to_time": "2021-01-01 08:00:00",
				"completed_qty": 1,
				"employee": employee,
			},
		)
		jc1.save()

		# add a new entry in same time slice
		jc2.append(
			"time_logs",
			{
				"from_time": "2021-01-01 00:01:00",
				"to_time": "2021-01-01 06:00:00",
				"completed_qty": 1,
				"employee": employee,
			},
		)
		self.assertRaises(OverlapError, jc2.save)

	def test_job_card_overlap_with_capacity(self):
		wo2 = make_wo_order_test_record(item="_Test FG Item 2", qty=2)

		workstation = make_workstation(workstation_name=random_string(5)).name
		frappe.db.set_value("Workstation", workstation, "production_capacity", 1)

		jc1 = frappe.get_last_doc("Job Card", {"work_order": self.work_order.name})
		jc2 = frappe.get_last_doc("Job Card", {"work_order": wo2.name})

		jc1.workstation = workstation
		jc1.append(
			"time_logs",
			{"from_time": "2021-01-01 00:00:00", "to_time": "2021-01-01 08:00:00", "completed_qty": 1},
		)
		jc1.save()

		jc2.workstation = workstation

		# add a new entry in same time slice
		jc2.append(
			"time_logs",
			{"from_time": "2021-01-01 00:01:00", "to_time": "2021-01-01 06:00:00", "completed_qty": 1},
		)
		self.assertRaises(OverlapError, jc2.save)

		frappe.db.set_value("Workstation", workstation, "production_capacity", 2)
		jc2.load_from_db()

		jc2.workstation = workstation

		# add a new entry in same time slice
		jc2.append(
			"time_logs",
			{"from_time": "2021-01-01 00:01:00", "to_time": "2021-01-01 06:00:00", "completed_qty": 1},
		)

		jc2.save()
		self.assertTrue(jc2.name)

	def test_job_card_multiple_materials_transfer(self):
		"Test transferring RMs separately against Job Card with multiple RMs."
		self.transfer_material_against = "Job Card"
		self.source_warehouse = "Stores - _TC"

		self.generate_required_stock(self.work_order)

		job_card_name = frappe.db.get_value("Job Card", {"work_order": self.work_order.name})
		job_card = frappe.get_doc("Job Card", job_card_name)

		transfer_entry_1 = make_stock_entry_from_jc(job_card_name)
		del transfer_entry_1.items[1]  # transfer only 1 of 2 RMs
		transfer_entry_1.insert()
		transfer_entry_1.submit()

		job_card.reload()

		self.assertEqual(transfer_entry_1.fg_completed_qty, 2)
		self.assertEqual(job_card.transferred_qty, 2)

		# transfer second RM
		transfer_entry_2 = make_stock_entry_from_jc(job_card_name)
		del transfer_entry_2.items[0]
		transfer_entry_2.insert()
		transfer_entry_2.submit()

		# 'For Quantity' here will be 0 since
		# transfer was made for 2 fg qty in first transfer Stock Entry
		self.assertEqual(transfer_entry_2.fg_completed_qty, 0)

	@change_settings("Manufacturing Settings", {"job_card_excess_transfer": 1})
	def test_job_card_excess_material_transfer(self):
		"Test transferring more than required RM against Job Card."
		self.transfer_material_against = "Job Card"
		self.source_warehouse = "Stores - _TC"

		self.generate_required_stock(self.work_order)

		job_card = frappe.get_last_doc("Job Card", {"work_order": self.work_order.name})
		self.assertEqual(job_card.status, "Open")

		# fully transfer both RMs
		transfer_entry_1 = make_stock_entry_from_jc(job_card.name)
		transfer_entry_1.insert()
		transfer_entry_1.submit()

		# transfer extra qty of both RM due to previously damaged RM
		transfer_entry_2 = make_stock_entry_from_jc(job_card.name)
		# deliberately change 'For Quantity'
		transfer_entry_2.fg_completed_qty = 1
		transfer_entry_2.items[0].qty = 5
		transfer_entry_2.items[1].qty = 3
		transfer_entry_2.insert()
		transfer_entry_2.submit()

		job_card.reload()
		self.assertGreater(job_card.transferred_qty, job_card.for_quantity)

		# Check if 'For Quantity' is negative
		# as 'transferred_qty' > Qty to Manufacture
		transfer_entry_3 = make_stock_entry_from_jc(job_card.name)
		self.assertEqual(transfer_entry_3.fg_completed_qty, 0)

		job_card.append(
			"time_logs",
			{"from_time": "2021-01-01 00:01:00", "to_time": "2021-01-01 06:00:00", "completed_qty": 2},
		)
		job_card.save()
		job_card.submit()

		# JC is Completed with excess transfer
		self.assertEqual(job_card.status, "Completed")

	def test_job_card_time_log_blocked_until_material_transfer(self):
		"Time logs must wait for the transfer when RMs move against Job Card."
		self.transfer_material_against = "Job Card"
		self.source_warehouse = "Stores - _TC"

		self.generate_required_stock(self.work_order)
		job_card = frappe.get_last_doc("Job Card", {"work_order": self.work_order.name})

		self.assertRaises(
			frappe.ValidationError, job_card.add_time_log, frappe._dict(start_time=now(), employees=[])
		)

		transfer_entry = make_stock_entry_from_jc(job_card.name)
		transfer_entry.insert()
		transfer_entry.submit()

		job_card.reload()
		job_card.add_time_log(frappe._dict(start_time=now(), employees=[]))
		self.assertTrue(job_card.time_logs)

	@change_settings("Manufacturing Settings", {"job_card_excess_transfer": 0})
	def test_job_card_excess_material_transfer_block(self):
		self.transfer_material_against = "Job Card"
		self.source_warehouse = "Stores - _TC"

		self.generate_required_stock(self.work_order)

		job_card_name = frappe.db.get_value("Job Card", {"work_order": self.work_order.name})

		# fully transfer both RMs
		transfer_entry_1 = make_stock_entry_from_jc(job_card_name)
		transfer_entry_1.insert()
		transfer_entry_1.submit()

		# transfer extra qty of both RM due to previously damaged RM
		transfer_entry_2 = make_stock_entry_from_jc(job_card_name)
		# deliberately change 'For Quantity'
		transfer_entry_2.fg_completed_qty = 1
		transfer_entry_2.items[0].qty = 5
		transfer_entry_2.items[1].qty = 3
		transfer_entry_2.insert()
		self.assertRaises(JobCardOverTransferError, transfer_entry_2.submit)

	@change_settings("Manufacturing Settings", {"job_card_excess_transfer": 0})
	def test_job_card_excess_material_transfer_with_no_reference(self):
		self.transfer_material_against = "Job Card"
		self.source_warehouse = "Stores - _TC"

		self.generate_required_stock(self.work_order)

		job_card_name = frappe.db.get_value("Job Card", {"work_order": self.work_order.name})

		# fully transfer both RMs
		transfer_entry_1 = make_stock_entry_from_jc(job_card_name)
		row = transfer_entry_1.items[0]

		# Add new row without reference of the job card item
		transfer_entry_1.append(
			"items",
			{
				"item_code": row.item_code,
				"item_name": row.item_name,
				"item_group": row.item_group,
				"qty": row.qty,
				"uom": row.uom,
				"conversion_factor": row.conversion_factor,
				"stock_uom": row.stock_uom,
				"basic_rate": row.basic_rate,
				"basic_amount": row.basic_amount,
				"expense_account": row.expense_account,
				"cost_center": row.cost_center,
				"s_warehouse": row.s_warehouse,
				"t_warehouse": row.t_warehouse,
			},
		)

		self.assertRaises(frappe.ValidationError, transfer_entry_1.insert)

	def test_job_card_partial_material_transfer(self):
		"Test partial material transfer against Job Card"
		self.transfer_material_against = "Job Card"
		self.source_warehouse = "Stores - _TC"

		self.generate_required_stock(self.work_order)

		job_card = frappe.get_last_doc("Job Card", {"work_order": self.work_order.name})

		# partially transfer
		transfer_entry = make_stock_entry_from_jc(job_card.name)
		transfer_entry.fg_completed_qty = 1
		transfer_entry.get_items()
		transfer_entry.insert()
		transfer_entry.submit()

		job_card.reload()
		self.assertEqual(job_card.transferred_qty, 1)
		self.assertEqual(transfer_entry.items[0].qty, 5)
		self.assertEqual(transfer_entry.items[1].qty, 3)

		# transfer remaining
		transfer_entry_2 = make_stock_entry_from_jc(job_card.name)

		self.assertEqual(transfer_entry_2.fg_completed_qty, 1)
		self.assertEqual(transfer_entry_2.items[0].qty, 5)
		self.assertEqual(transfer_entry_2.items[1].qty, 3)

		transfer_entry_2.insert()
		transfer_entry_2.submit()

		job_card.reload()
		self.assertEqual(job_card.transferred_qty, 2)

		transfer_entry_2.cancel()
		transfer_entry.cancel()

		job_card.reload()
		self.assertEqual(job_card.transferred_qty, 0.0)

	def test_work_order_transferred_qty_with_multiple_job_cards(self):
		create_bom_with_multiple_operations()
		work_order = make_wo_with_transfer_against_jc()
		self.generate_required_stock(work_order)

		job_cards = frappe.get_all(
			"Job Card",
			filters={"work_order": work_order.name},
			pluck="name",
			order_by="sequence_id",
		)
		completed_qty = (4, 3)

		for job_card_name, qty in zip(job_cards, completed_qty, strict=True):
			job_card = frappe.get_doc("Job Card", job_card_name)
			job_card.for_quantity = qty
			job_card.save()

			transfer_entry = make_stock_entry_from_jc(job_card.name)
			transfer_entry.fg_completed_qty = qty
			transfer_entry.get_items()
			transfer_entry.submit()

			job_card.reload()
			job_card.append(
				"time_logs",
				{
					"from_time": now(),
					"to_time": add_to_date(now(), hours=1),
					"completed_qty": qty,
				},
			)
			job_card.submit()

		work_order.reload()
		self.assertEqual(work_order.material_transferred_for_manufacturing, min(completed_qty))

		# Refreshing required items must not replace the Job Card roll-up with the sum
		# of FG quantities from Material Transfer Stock Entries (4 + 3).
		work_order.update_required_items()
		work_order.reload()
		self.assertEqual(work_order.material_transferred_for_manufacturing, min(completed_qty))

	def test_job_card_material_transfer_correctness(self):
		"""
		1. Test if only current Job Card Items are pulled in a Stock Entry against a Job Card
		2. Test impact of changing 'For Qty' in such a Stock Entry
		"""
		create_bom_with_multiple_operations()
		work_order = make_wo_with_transfer_against_jc()

		job_card_name = frappe.db.get_value(
			"Job Card", {"work_order": work_order.name, "operation": "Test Operation A"}
		)
		job_card = frappe.get_doc("Job Card", job_card_name)

		self.assertEqual(len(job_card.items), 1)
		self.assertEqual(job_card.items[0].item_code, "_Test Item")

		# check if right items are mapped in transfer entry
		transfer_entry = make_stock_entry_from_jc(job_card_name)
		transfer_entry.insert()

		self.assertEqual(len(transfer_entry.items), 1)
		self.assertEqual(transfer_entry.items[0].item_code, "_Test Item")
		self.assertEqual(transfer_entry.items[0].qty, 4)

		# change 'For Qty' and check impact on items table
		# no.of items should be the same with qty change
		transfer_entry.fg_completed_qty = 2
		transfer_entry.get_items()

		self.assertEqual(len(transfer_entry.items), 1)
		self.assertEqual(transfer_entry.items[0].item_code, "_Test Item")
		self.assertEqual(transfer_entry.items[0].qty, 2)

	@change_settings(
		"Manufacturing Settings", {"add_corrective_operation_cost_in_finished_good_valuation": 1}
	)
	def test_corrective_costing(self):
		job_card = frappe.get_last_doc("Job Card", {"work_order": self.work_order.name})

		job_card.append(
			"time_logs",
			{"from_time": now(), "to_time": add_to_date(now(), hours=1), "completed_qty": 2},
		)
		job_card.submit()

		self.work_order.reload()
		original_cost = self.work_order.total_operating_cost

		# Create a corrective operation against it
		corrective_action = frappe.get_doc(
			doctype="Operation", is_corrective_operation=1, name=frappe.generate_hash()
		).insert()

		corrective_job_card = make_corrective_job_card(
			job_card.name, operation=corrective_action.name, for_operation=job_card.operation
		)
		corrective_job_card.hour_rate = 100
		corrective_job_card.insert()
		corrective_job_card.append(
			"time_logs",
			{
				"from_time": add_to_date(now(), hours=2),
				"to_time": add_to_date(now(), hours=2, minutes=30),
				"completed_qty": 2,
			},
		)
		corrective_job_card.submit()

		self.work_order.reload()
		cost_after_correction = self.work_order.total_operating_cost
		self.assertGreater(cost_after_correction, original_cost)

		corrective_job_card.cancel()
		self.work_order.reload()
		cost_after_cancel = self.work_order.total_operating_cost
		self.assertEqual(cost_after_cancel, original_cost)

	@change_settings(
		"Manufacturing Settings", {"add_corrective_operation_cost_in_finished_good_valuation": 1}
	)
	def test_if_corrective_jc_ops_cost_is_added_to_manufacture_stock_entry(self):
		wo = make_wo_order_test_record(
			item="_Test FG Item 2",
			qty=10,
			transfer_material_against=self.transfer_material_against,
			source_warehouse=self.source_warehouse,
		)
		self.generate_required_stock(wo)
		job_card = frappe.get_last_doc("Job Card", {"work_order": wo.name})
		job_card.update({"for_quantity": 4})
		job_card.append(
			"time_logs",
			{"from_time": now(), "to_time": add_to_date(now(), hours=1), "completed_qty": 4},
		)
		job_card.submit()

		corrective_action = frappe.get_doc(
			doctype="Operation", is_corrective_operation=1, name=frappe.generate_hash()
		).insert()

		corrective_job_card = make_corrective_job_card(
			job_card.name, operation=corrective_action.name, for_operation=job_card.operation
		)
		corrective_job_card.hour_rate = 100
		corrective_job_card.insert()
		corrective_job_card.append(
			"time_logs",
			{
				"from_time": add_to_date(now(), hours=2),
				"to_time": add_to_date(now(), hours=2, minutes=30),
				"completed_qty": 4,
			},
		)
		corrective_job_card.submit()
		wo.reload()

		from erpnext.manufacturing.doctype.work_order.work_order import (
			make_stock_entry as make_stock_entry_for_wo,
		)

		stock_entry = make_stock_entry_for_wo(wo.name, "Manufacture", qty=3)
		self.assertEqual(stock_entry.additional_costs[1].amount, 37.5)
		frappe.get_doc(stock_entry).submit()

		from erpnext.manufacturing.doctype.work_order.work_order import make_job_card

		make_job_card(
			wo.name,
			[{"name": wo.operations[0].name, "operation": "_Test Operation 1", "qty": 3, "pending_qty": 3}],
		)
		workstation = job_card.workstation
		job_card = frappe.get_last_doc("Job Card", {"work_order": wo.name})
		job_card.update({"for_quantity": 3})
		job_card.workstation = workstation
		job_card.append(
			"time_logs",
			{
				"from_time": add_to_date(now(), hours=3),
				"to_time": add_to_date(now(), hours=4),
				"completed_qty": 3,
			},
		)
		job_card.submit()

		corrective_job_card = make_corrective_job_card(
			job_card.name, operation=corrective_action.name, for_operation=job_card.operation
		)
		corrective_job_card.hour_rate = 80
		corrective_job_card.insert()
		corrective_job_card.append(
			"time_logs",
			{
				"from_time": add_to_date(now(), hours=4),
				"to_time": add_to_date(now(), hours=4, minutes=30),
				"completed_qty": 3,
			},
		)
		corrective_job_card.submit()
		wo.reload()

		stock_entry = make_stock_entry_for_wo(wo.name, "Manufacture", qty=4)
		self.assertEqual(stock_entry.additional_costs[1].amount, 52.5)

	def test_job_card_statuses(self):
		def assertStatus(status):
			jc.set_status()
			self.assertEqual(jc.status, status)

		jc = frappe.new_doc("Job Card")
		jc.process_loss_qty = 0
		jc.for_quantity = 2
		jc.transferred_qty = 1
		jc.total_completed_qty = 0
		assertStatus("Open")

		jc.transferred_qty = jc.for_quantity
		assertStatus("Material Transferred")

		jc.append("time_logs", {})
		assertStatus("Work In Progress")

		jc.docstatus = 1
		jc.total_completed_qty = jc.for_quantity
		assertStatus("Completed")

		jc.docstatus = 2
		assertStatus("Cancelled")

	def test_job_card_material_request_and_bom_details(self):
		from erpnext.stock.doctype.material_request.material_request import make_stock_entry

		create_bom_with_multiple_operations()
		work_order = make_wo_with_transfer_against_jc()

		job_card_name = frappe.db.get_value("Job Card", {"work_order": work_order.name}, "name")

		mr = make_material_request(job_card_name)
		mr.schedule_date = today()
		mr.submit()

		ste = make_stock_entry(mr.name)
		self.assertEqual(ste.purpose, "Material Transfer for Manufacture")
		self.assertEqual(ste.work_order, work_order.name)
		self.assertEqual(ste.job_card, job_card_name)
		self.assertEqual(ste.from_bom, 1.0)
		self.assertEqual(ste.bom_no, work_order.bom_no)

	def test_job_card_proccess_qty_and_completed_qty(self):
		from erpnext.manufacturing.doctype.routing.test_routing import (
			create_routing,
			setup_bom,
			setup_operations,
		)
		from erpnext.manufacturing.doctype.work_order.work_order import (
			make_stock_entry as make_stock_entry_for_wo,
		)
		from erpnext.stock.doctype.item.test_item import make_item
		from erpnext.stock.doctype.warehouse.test_warehouse import create_warehouse

		operations = [
			{"operation": "Test Operation A1", "workstation": "Test Workstation A", "time_in_mins": 30},
			{"operation": "Test Operation B1", "workstation": "Test Workstation A", "time_in_mins": 20},
		]

		make_test_records("UOM")

		warehouse = create_warehouse("Test Warehouse 123 for Job Card")

		setup_operations(operations)

		item_code = "Test Job Card Process Qty Item"
		for item in [item_code, item_code + "RM 1", item_code + "RM 2"]:
			if not frappe.db.exists("Item", item):
				make_item(
					item,
					{
						"item_name": item,
						"stock_uom": "Nos",
						"is_stock_item": 1,
					},
				)

		routing_doc = create_routing(routing_name="Testing Route", operations=operations)
		bom_doc = setup_bom(
			item_code=item_code,
			routing=routing_doc.name,
			raw_materials=[item_code + "RM 1", item_code + "RM 2"],
			source_warehouse=warehouse,
		)

		for row in bom_doc.items:
			make_stock_entry(
				item_code=row.item_code,
				target=row.source_warehouse,
				qty=10,
				basic_rate=100,
			)

		wo_doc = make_wo_order_test_record(
			production_item=item_code,
			bom_no=bom_doc.name,
			skip_transfer=1,
			from_wip_warehouse=1,
			wip_warehouse=warehouse,
			source_warehouse=warehouse,
		)

		for row in routing_doc.operations:
			self.assertEqual(row.sequence_id, row.idx)

		first_job_card = frappe.get_all(
			"Job Card",
			filters={"work_order": wo_doc.name, "sequence_id": 1},
			fields=["name"],
			order_by="sequence_id",
			limit=1,
		)[0].name

		jc = frappe.get_doc("Job Card", first_job_card)
		for row in jc.scheduled_time_logs:
			jc.append(
				"time_logs",
				{
					"from_time": row.from_time,
					"to_time": row.to_time,
					"time_in_mins": row.time_in_mins,
				},
			)

		jc.time_logs[0].completed_qty = 8
		jc.save()
		jc.submit()

		self.assertEqual(jc.process_loss_qty, 2)
		self.assertEqual(jc.for_quantity, 10)

		second_job_card = frappe.get_all(
			"Job Card",
			filters={"work_order": wo_doc.name, "sequence_id": 2},
			fields=["name"],
			order_by="sequence_id",
			limit=1,
		)[0].name

		jc2 = frappe.get_doc("Job Card", second_job_card)
		for row in jc2.scheduled_time_logs:
			jc2.append(
				"time_logs",
				{
					"from_time": row.from_time,
					"to_time": row.to_time,
					"time_in_mins": row.time_in_mins,
				},
			)
		jc2.time_logs[0].completed_qty = 10

		self.assertRaises(frappe.ValidationError, jc2.save)

		jc2.load_from_db()
		for row in jc2.scheduled_time_logs:
			jc2.append(
				"time_logs",
				{
					"from_time": row.from_time,
					"to_time": row.to_time,
					"time_in_mins": row.time_in_mins,
				},
			)

		jc2.time_logs[0].completed_qty = 8
		jc2.save()
		jc2.submit()

		self.assertEqual(jc2.for_quantity, 10)
		self.assertEqual(jc2.process_loss_qty, 2)

		s = frappe.get_doc(make_stock_entry_for_wo(wo_doc.name, "Manufacture", 10))
		s.submit()

		self.assertEqual(s.process_loss_qty, 2)

		wo_doc.reload()
		for row in wo_doc.operations:
			self.assertEqual(row.completed_qty, 8)
			self.assertEqual(row.process_loss_qty, 2)

		self.assertEqual(wo_doc.produced_qty, 8)
		self.assertEqual(wo_doc.process_loss_qty, 2)
		self.assertEqual(wo_doc.status, "Completed")

<<<<<<< HEAD
=======
	def make_two_operation_work_order(self, qty=10):
		from erpnext.manufacturing.doctype.routing.test_routing import (
			create_routing,
			setup_bom,
			setup_operations,
		)
		from erpnext.stock.doctype.item.test_item import make_item
		from erpnext.stock.doctype.warehouse.test_warehouse import create_warehouse

		operations = [
			{"operation": "Test Operation A1", "workstation": "Test Workstation A", "time_in_mins": 30},
			{"operation": "Test Operation B1", "workstation": "Test Workstation A", "time_in_mins": 20},
		]

		warehouse = create_warehouse("Test Warehouse 123 for Job Card")
		setup_operations(operations)

		item_code = "Test Job Card Process Qty Item"
		for item in [item_code, item_code + "RM 1", item_code + "RM 2"]:
			if not frappe.db.exists("Item", item):
				make_item(item, {"item_name": item, "stock_uom": "Nos", "is_stock_item": 1})

		routing_doc = create_routing(routing_name="Testing Route", operations=operations)
		bom_doc = setup_bom(
			item_code=item_code,
			routing=routing_doc.name,
			raw_materials=[item_code + "RM 1", item_code + "RM 2"],
			source_warehouse=warehouse,
		)

		for row in bom_doc.items:
			make_stock_entry(item_code=row.item_code, target=row.source_warehouse, qty=qty, basic_rate=100)

		return make_wo_order_test_record(
			production_item=item_code,
			bom_no=bom_doc.name,
			qty=qty,
			skip_transfer=1,
			wip_warehouse=warehouse,
			source_warehouse=warehouse,
		)

	def test_completion_qty_capped_by_previous_operation(self):
		wo_doc = self.make_two_operation_work_order()
		job_cards = frappe.get_all(
			"Job Card",
			filters={"work_order": wo_doc.name},
			fields=["name", "sequence_id"],
			order_by="sequence_id",
		)

		jc1 = frappe.get_doc("Job Card", job_cards[0].name)
		self.assertIsNone(jc1.get_max_completable_qty())

		jc1.append(
			"time_logs",
			{"from_time": now(), "to_time": add_to_date(now(), minutes=30), "completed_qty": 8},
		)
		jc1.save()
		jc1.submit()
		self.assertEqual(jc1.process_loss_qty, 2)

		jc2 = frappe.get_doc("Job Card", job_cards[1].name)
		self.assertEqual(jc2.get_max_completable_qty(), 8)

		jc2.append("time_logs", {"from_time": add_to_date(now(), minutes=40)})
		jc2.save()

		self.assertRaises(
			frappe.ValidationError,
			jc2.complete_job_card,
			qty=10,
			for_quantity=10,
			pending_qty=0,
			process_loss_qty=0,
			end_time=add_to_date(now(), minutes=70),
		)

		self.complete_second_operation_and_finish(wo_doc, jc2.name)

	def complete_second_operation_and_finish(self, wo_doc, job_card):
		from erpnext.manufacturing.doctype.work_order.mapper import (
			make_stock_entry as make_stock_entry_for_wo,
		)

		jc2 = frappe.get_doc("Job Card", job_card)
		jc2.time_logs[0].completed_qty = 7
		jc2.time_logs[0].to_time = add_to_date(now(), minutes=70)
		jc2.save()
		self.assertEqual(jc2.process_loss_qty, 3)
		jc2.submit()

		se = frappe.get_doc(make_stock_entry_for_wo(wo_doc.name, "Manufacture", 10))
		se.submit()

		self.assertEqual(se.process_loss_qty, 3)
		fg_qty = sum(d.qty for d in se.items if d.is_finished_item)
		self.assertEqual(flt(fg_qty), 7)

		wo_doc.reload()
		self.assertEqual(wo_doc.produced_qty, 7)
		self.assertEqual(wo_doc.process_loss_qty, 3)
		self.assertEqual(wo_doc.status, "Completed")

	def get_first_job_card(self, work_order):
		return frappe.get_doc(
			"Job Card",
			frappe.get_all(
				"Job Card",
				filters={"work_order": work_order},
				order_by="sequence_id, creation",
				limit=1,
				pluck="name",
			)[0],
		)

	def test_stock_uom_is_set_from_the_produced_item(self):
		work_order = make_wo_order_test_record(item="_Test FG Item 2", qty=5)

		job_card = self.get_first_job_card(work_order.name)
		item_code = job_card.finished_good or job_card.production_item

		self.assertEqual(job_card.stock_uom, frappe.db.get_value("Item", item_code, "stock_uom"))

	def test_completion_qty_reduces_for_quantity_without_process_loss(self):
		work_order = make_wo_order_test_record(item="_Test FG Item 2", qty=5)

		job_card = self.get_first_job_card(work_order.name)
		job_card.append("time_logs", {"from_time": "2024-03-01 08:00:00"})
		job_card.save()

		job_card.complete_job_card(
			qty=3,
			for_quantity=3,
			pending_qty=0,
			process_loss_qty=0,
			end_time="2024-03-01 09:00:00",
		)

		job_card.reload()
		self.assertEqual(flt(job_card.for_quantity), 3)
		self.assertEqual(flt(job_card.total_completed_qty), 3)
		self.assertEqual(flt(job_card.process_loss_qty), 0)

	def test_completion_allows_zero_completed_qty(self):
		work_order = make_wo_order_test_record(item="_Test FG Item 2", qty=5)

		job_card = self.get_first_job_card(work_order.name)
		job_card.append("time_logs", {"from_time": "2024-03-01 08:00:00"})
		job_card.save()

		job_card.complete_job_card(
			qty=0,
			for_quantity=5,
			pending_qty=0,
			process_loss_qty=5,
			end_time="2024-03-01 09:00:00",
		)

		job_card.reload()
		self.assertEqual(flt(job_card.total_completed_qty), 0)
		self.assertEqual(flt(job_card.process_loss_qty), 5)

		job_card.submit()
		self.assertEqual(job_card.docstatus, 1)

	def test_completion_overwrites_existing_completed_qty_with_zero(self):
		work_order = make_wo_order_test_record(item="_Test FG Item 2", qty=5)

		job_card = self.get_first_job_card(work_order.name)
		job_card.append("time_logs", {"from_time": "2024-03-01 08:00:00", "completed_qty": 5})

		job_card.complete_job_card(
			qty=0,
			for_quantity=5,
			pending_qty=0,
			process_loss_qty=5,
			end_time="2024-03-01 09:00:00",
		)

		job_card.reload()
		self.assertEqual(flt(job_card.total_completed_qty), 0)
		self.assertEqual(flt(job_card.process_loss_qty), 5)
		self.assertEqual(flt(job_card.time_logs[0].completed_qty), 0)

		job_card.submit()
		self.assertEqual(job_card.docstatus, 1)

	def test_completion_qty_keeps_for_quantity_across_cycles(self):
		work_order = make_wo_order_test_record(item="_Test FG Item 2", qty=5)

		job_card = self.get_first_job_card(work_order.name)
		job_card.append("time_logs", {"from_time": "2024-03-02 08:00:00"})
		job_card.save()

		job_card.complete_job_card(
			qty=3,
			for_quantity=5,
			pending_qty=2,
			process_loss_qty=0,
			end_time="2024-03-02 09:00:00",
		)

		job_card.reload()
		self.assertEqual(flt(job_card.for_quantity), 5)
		self.assertEqual(flt(job_card.pending_qty), 2)
		self.assertEqual(flt(job_card.process_loss_qty), 0)

		job_card.append("time_logs", {"from_time": "2024-03-02 10:00:00"})
		job_card.save()

		job_card.complete_job_card(
			qty=2,
			for_quantity=2,
			pending_qty=0,
			process_loss_qty=0,
			end_time="2024-03-02 11:00:00",
		)

		job_card.reload()
		self.assertEqual(flt(job_card.for_quantity), 5)
		self.assertEqual(flt(job_card.total_completed_qty), 5)
		self.assertEqual(flt(job_card.process_loss_qty), 0)

>>>>>>> 1d8ce1e (fix(stock): allow zero completed quantity and handle process loss in job cards (#59104))
	def test_op_cost_calculation(self):
		from erpnext.manufacturing.doctype.routing.test_routing import (
			create_routing,
			setup_bom,
			setup_operations,
		)
		from erpnext.manufacturing.doctype.work_order.work_order import make_job_card
		from erpnext.manufacturing.doctype.work_order.work_order import (
			make_stock_entry as make_stock_entry_for_wo,
		)
		from erpnext.stock.doctype.item.test_item import make_item
		from erpnext.stock.doctype.warehouse.test_warehouse import create_warehouse

		suffix = random_string(5)
		workstation = make_workstation(
			workstation_name=f"Test Workstation Z {suffix}", hour_rate_rent=240, hour_rate_labour=0
		)
		workstation.update(
			{
				"hour_rate_rent": 240,
				"hour_rate_labour": 0,
				"hour_rate_electricity": 0,
				"hour_rate_consumable": 0,
			}
		)
		workstation.save()
		operations = [
			{
				"operation": f"Test Operation A1 {suffix}",
				"workstation": workstation.name,
				"time_in_mins": 30,
			},
		]

		warehouse = create_warehouse(f"Test Warehouse 123 for Job Card {suffix}")
		setup_operations(operations)

		item_code = f"Test Job Card Process Qty Item {suffix}"
		for item in [item_code, item_code + "RM 1", item_code + "RM 2"]:
			if not frappe.db.exists("Item", item):
				make_item(
					item,
					{
						"item_name": item,
						"stock_uom": "Nos",
						"is_stock_item": 1,
					},
				)

		routing_doc = create_routing(routing_name="Testing Route", operations=operations)
		bom_doc = setup_bom(
			item_code=item_code,
			routing=routing_doc.name,
			raw_materials=[item_code + "RM 1", item_code + "RM 2"],
			source_warehouse=warehouse,
		)

		for row in bom_doc.items:
			make_stock_entry(
				item_code=row.item_code,
				target=row.source_warehouse,
				qty=10,
				basic_rate=100,
			)

		wo_doc = make_wo_order_test_record(
			production_item=item_code,
			bom_no=bom_doc.name,
			qty=10,
			skip_transfer=1,
			wip_warehouse=warehouse,
			source_warehouse=warehouse,
		)

		first_job_card = frappe.get_all(
			"Job Card",
			filters={"work_order": wo_doc.name, "sequence_id": 1},
			fields=["name"],
			order_by="sequence_id",
			limit=1,
		)[0].name

		jc = frappe.get_doc("Job Card", first_job_card)
		from_time = "2025-01-01 09:00:00"
		for _ in jc.scheduled_time_logs:
			jc.append(
				"time_logs",
				{
					"from_time": from_time,
					"to_time": add_to_date(from_time, minutes=1),
					"completed_qty": 4,
				},
			)
		jc.for_quantity = 4
		jc.save()
		jc.submit()

		s1 = frappe.get_doc(make_stock_entry_for_wo(wo_doc.name, "Manufacture", 4))
		s1.submit()

		wo_doc.reload()
		precision = s1.additional_costs[0].precision("amount")
		self.assertEqual(
			flt(s1.additional_costs[0].amount, precision),
			flt(wo_doc.operations[0].actual_operating_cost, precision),
		)

		make_job_card(
			wo_doc.name,
			[
				{
					"name": wo_doc.operations[0].name,
					"operation": operations[0]["operation"],
					"workstation": wo_doc.operations[0].workstation,
					"qty": 6,
					"pending_qty": 6,
				}
			],
		)

		job_card = frappe.get_last_doc("Job Card", {"work_order": wo_doc.name})
		from_time = "2025-01-01 10:00:00"
		job_card.append(
			"time_logs",
			{
				"from_time": from_time,
				"to_time": add_to_date(from_time, minutes=2),
				"completed_qty": 6,
			},
		)
		job_card.for_quantity = 6
		job_card.save()
		job_card.submit()

		s2 = frappe.get_doc(make_stock_entry_for_wo(wo_doc.name, "Manufacture", 6))
		wo_doc.reload()
		precision = s2.additional_costs[0].precision("amount")
		self.assertEqual(
			flt(s2.additional_costs[0].amount, precision),
			flt(wo_doc.operations[0].actual_operating_cost - s1.additional_costs[0].amount, precision),
		)

	@change_settings("Manufacturing Settings", {"overproduction_percentage_for_work_order": 100})
	def test_operating_cost_with_overproduction(self):
		from erpnext.manufacturing.doctype.routing.test_routing import (
			create_routing,
			setup_bom,
			setup_operations,
		)
		from erpnext.manufacturing.doctype.work_order.work_order import make_job_card
		from erpnext.manufacturing.doctype.work_order.work_order import (
			make_stock_entry as make_stock_entry_for_wo,
		)
		from erpnext.stock.doctype.item.test_item import make_item
		from erpnext.stock.doctype.warehouse.test_warehouse import create_warehouse

		suffix = random_string(5)
		workstation = make_workstation(
			workstation_name=f"Test Workstation for Overproduction {suffix}",
			hour_rate_rent=10,
			hour_rate_labour=10,
		)
		workstation.update(
			{
				"hour_rate_rent": 10,
				"hour_rate_labour": 10,
				"hour_rate_electricity": 0,
				"hour_rate_consumable": 0,
			}
		)
		workstation.save()
		operations = [
			{"operation": f"Test Operation 1 {suffix}", "workstation": workstation.name, "time_in_mins": 30},
			{"operation": f"Test Operation 2 {suffix}", "workstation": workstation.name, "time_in_mins": 30},
		]
		warehouse = create_warehouse(f"Test Warehouse for Overproduction {suffix}")
		setup_operations(operations)

		fg = make_item(f"Test FG for Overproduction {suffix}", {"stock_uom": "Nos", "is_stock_item": 1})
		rm = make_item(f"Test RM for Overproduction {suffix}", {"stock_uom": "Nos", "is_stock_item": 1})

		routing_doc = create_routing(routing_name=f"Testing Route {suffix}", operations=operations)
		bom_doc = setup_bom(
			item_code=fg.name,
			routing=routing_doc.name,
			raw_materials=[rm.name],
			source_warehouse=warehouse,
		)

		for row in bom_doc.items:
			make_stock_entry(
				item_code=row.item_code,
				target=row.source_warehouse,
				qty=100,
				basic_rate=100,
			)

		wo_doc = make_wo_order_test_record(
			production_item=fg.name,
			bom_no=bom_doc.name,
			qty=10,
			skip_transfer=1,
			source_warehouse=warehouse,
		)

		first_operation = frappe.get_all(
			"Job Card",
			filters={"work_order": wo_doc.name, "sequence_id": 1},
			fields=["name"],
			order_by="sequence_id",
			limit=1,
		)[0].name

		jc = frappe.get_doc("Job Card", first_operation)
		from_time = "2025-01-02 09:00:00"
		for _ in jc.scheduled_time_logs:
			jc.append(
				"time_logs",
				{
					"from_time": from_time,
					"to_time": add_to_date(from_time, days=1),
					"completed_qty": 4,
				},
			)
		jc.for_quantity = 4
		jc.save()
		jc.submit()

		second_operation = frappe.get_all(
			"Job Card",
			filters={"work_order": wo_doc.name, "sequence_id": 2},
			fields=["name"],
			order_by="sequence_id",
			limit=1,
		)[0].name

		jc = frappe.get_doc("Job Card", second_operation)
		from_time = "2025-01-05 09:00:00"
		for _ in jc.scheduled_time_logs:
			jc.append(
				"time_logs",
				{
					"from_time": from_time,
					"to_time": add_to_date(from_time, days=2),
					"completed_qty": 4,
				},
			)
		jc.for_quantity = 4
		jc.save()
		jc.submit()

		s = frappe.get_doc(make_stock_entry_for_wo(wo_doc.name, "Manufacture", 6))  # overproduction
		s.submit()

		def assert_operating_costs(stock_entry, qty, previous_entries):
			wo_doc.reload()
			for idx, operation in enumerate(wo_doc.operations):
				consumed_cost = sum(
					entry.additional_costs[idx].amount for entry in previous_entries if entry.docstatus == 1
				)
				consumed_qty = sum(
					entry.additional_costs[idx].qty for entry in previous_entries if entry.docstatus == 1
				)
				remaining_cost = operation.actual_operating_cost - consumed_cost
				remaining_qty = operation.completed_qty - consumed_qty
				precision = stock_entry.additional_costs[idx].precision("amount")
				expected_cost = flt(remaining_cost / remaining_qty * min(remaining_qty, qty), precision)

				self.assertEqual(flt(stock_entry.additional_costs[idx].amount, precision), expected_cost)

		assert_operating_costs(s, 6, [])

		make_job_card(
			wo_doc.name,
			[
				{
					"name": wo_doc.operations[0].name,
					"operation": operations[0]["operation"],
					"workstation": wo_doc.operations[0].workstation,
					"qty": 2,
					"pending_qty": 2,
				}
			],
		)

		job_card = frappe.get_last_doc("Job Card", {"work_order": wo_doc.name})
		from_time = "2025-01-09 09:00:00"
		job_card.append(
			"time_logs",
			{
				"from_time": from_time,
				"to_time": add_to_date(from_time, days=1),
				"completed_qty": 2,
			},
		)
		job_card.for_quantity = 2
		job_card.save()
		job_card.submit()

		make_job_card(
			wo_doc.name,
			[
				{
					"name": wo_doc.operations[1].name,
					"operation": operations[1]["operation"],
					"workstation": wo_doc.operations[1].workstation,
					"qty": 2,
					"pending_qty": 2,
				}
			],
		)

		job_card = frappe.get_last_doc("Job Card", {"work_order": wo_doc.name})
		from_time = "2025-01-12 09:00:00"
		job_card.append(
			"time_logs",
			{
				"from_time": from_time,
				"to_time": add_to_date(from_time, days=2),
				"completed_qty": 2,
			},
		)
		job_card.for_quantity = 2
		job_card.save()
		job_card.submit()

		s2 = frappe.get_doc(make_stock_entry_for_wo(wo_doc.name, "Manufacture", 1))
		s2.submit()

		assert_operating_costs(s2, 1, [s])

		make_job_card(
			wo_doc.name,
			[
				{
					"name": wo_doc.operations[0].name,
					"operation": operations[0]["operation"],
					"workstation": wo_doc.operations[0].workstation,
					"qty": 2,
					"pending_qty": 2,
				}
			],
		)

		job_card = frappe.get_last_doc("Job Card", {"work_order": wo_doc.name})
		from_time = "2025-01-16 09:00:00"
		job_card.append(
			"time_logs",
			{
				"from_time": from_time,
				"to_time": add_to_date(from_time, days=1),
				"completed_qty": 2,
			},
		)
		job_card.for_quantity = 2
		job_card.save()
		job_card.submit()

		make_job_card(
			wo_doc.name,
			[
				{
					"name": wo_doc.operations[1].name,
					"operation": operations[1]["operation"],
					"workstation": wo_doc.operations[1].workstation,
					"qty": 2,
					"pending_qty": 2,
				}
			],
		)

		job_card = frappe.get_last_doc("Job Card", {"work_order": wo_doc.name})
		from_time = "2025-01-19 09:00:00"
		job_card.append(
			"time_logs",
			{
				"from_time": from_time,
				"to_time": add_to_date(from_time, days=2),
				"completed_qty": 2,
			},
		)
		job_card.for_quantity = 2
		job_card.save()
		job_card.submit()

		s3 = frappe.get_doc(make_stock_entry_for_wo(wo_doc.name, "Manufacture", 2))
		s3.submit()

		assert_operating_costs(s3, 2, [s, s2])

		s2.cancel()

		s4 = frappe.get_doc(make_stock_entry_for_wo(wo_doc.name, "Manufacture", 3))
		s4.submit()

		assert_operating_costs(s4, 3, [s, s3])


def create_bom_with_multiple_operations():
	"Create a BOM with multiple operations and Material Transfer against Job Card"
	from erpnext.manufacturing.doctype.operation.test_operation import make_operation

	test_record = frappe.get_test_records("BOM")[2]
	bom_doc = frappe.get_doc(test_record)

	row = {
		"operation": "Test Operation A",
		"workstation": "_Test Workstation A",
		"hour_rate_rent": 300,
		"time_in_mins": 60,
	}
	make_workstation(row)
	make_operation(row)

	bom_doc.append(
		"operations",
		{
			"operation": "Test Operation A",
			"description": "Test Operation A",
			"workstation": "_Test Workstation A",
			"hour_rate": 300,
			"time_in_mins": 60,
			"operating_cost": 100,
		},
	)

	bom_doc.transfer_material_against = "Job Card"
	bom_doc.save()
	bom_doc.submit()

	return bom_doc


def make_wo_with_transfer_against_jc():
	"Create a WO with multiple operations and Material Transfer against Job Card"

	work_order = make_wo_order_test_record(
		item="_Test FG Item 2",
		qty=4,
		transfer_material_against="Job Card",
		source_warehouse="Stores - _TC",
		do_not_submit=True,
	)
	work_order.required_items[0].operation = "Test Operation A"
	work_order.required_items[1].operation = "_Test Operation 1"
	work_order.submit()

	return work_order


<<<<<<< HEAD
def make_bom_for_jc_tests():
	test_records = frappe.get_test_records("BOM")
	bom = frappe.copy_doc(test_records[2])
	bom.set_rate_of_sub_assembly_item_based_on_bom = 0
	bom.rm_cost_as_per = "Valuation Rate"
	bom.items[0].uom = "_Test UOM 1"
	bom.items[0].conversion_factor = 5
	bom.insert()
=======
def create_semi_fg_bom(semi_fg_item, raw_item, inspection_required):
	bom = frappe.new_doc("BOM")
	bom.company = "Wind Power LLC"
	bom.item = semi_fg_item
	bom.quantity = 1
	bom.inspection_required = inspection_required
	bom.append("items", {"item_code": raw_item, "qty": 1})
	bom.submit()
	return bom.name


class TestJobCardLogic(ERPNextTestSuite):
	"""Field-level validations and pure quantity/capacity helpers, exercised on the
	document directly so they don't need a Work Order / BOM (the integration suite does)."""

	def test_processing_a_submitted_or_cancelled_card_is_blocked(self):
		submitted = frappe.new_doc("Job Card")
		submitted.docstatus = 1
		self.assertRaises(frappe.ValidationError, submitted.validate_docstatus)

		cancelled = frappe.new_doc("Job Card")
		cancelled.docstatus = 2
		self.assertRaises(frappe.ValidationError, cancelled.validate_docstatus)

	def test_complete_job_card_qty_guards(self):
		jc = frappe.new_doc("Job Card")
		jc.for_quantity = 5
		jc.validate_complete_job_card_qty(frappe._dict(pending_qty=3))  # within range -> passes
		self.assertRaises(frappe.ValidationError, jc.validate_complete_job_card_qty, frappe._dict(qty=-1))
		self.assertRaises(
			frappe.ValidationError, jc.validate_complete_job_card_qty, frappe._dict(pending_qty=-1)
		)
		self.assertRaises(
			frappe.ValidationError, jc.validate_complete_job_card_qty, frappe._dict(process_loss_qty=-1)
		)
		self.assertRaises(
			frappe.ValidationError, jc.validate_complete_job_card_qty, frappe._dict(pending_qty=10)
		)

	def test_qty_in_messages_carries_the_uom(self):
		jc = frappe.new_doc("Job Card")
		jc.stock_uom = "Nos"

		self.assertEqual(jc.get_qty_with_uom(5), "5.0 Nos")
		self.assertEqual(jc.get_qty_with_uom(0), "0.0 Nos")

	def test_completion_qty_split_must_add_up(self):
		jc = frappe.new_doc("Job Card")
		jc.for_quantity = 5

		# 3 completed + 2 pending + 0 lost == 5 to manufacture -> passes
		jc.validate_complete_job_card_qty(
			frappe._dict(for_quantity=5, qty=3, pending_qty=2, process_loss_qty=0)
		)
		jc.validate_complete_job_card_qty(
			frappe._dict(for_quantity=5, qty=0, pending_qty=0, process_loss_qty=5)
		)
		jc.validate_complete_job_card_qty(
			frappe._dict(for_quantity=5, qty=0, pending_qty=5, process_loss_qty=0)
		)

		self.assertRaises(
			frappe.ValidationError,
			jc.validate_complete_job_card_qty,
			frappe._dict(for_quantity=3, qty=3, pending_qty=2, process_loss_qty=0),
		)

	def test_completed_qty_must_reconcile_with_for_quantity(self):
		jc = frappe.new_doc("Job Card")
		jc.for_quantity = 10
		jc.total_completed_qty = 6
		jc.process_loss_qty = 0
		jc.pending_qty = 0
		# 6 + 0 + 0 != 10 -> throws
		self.assertRaises(frappe.ValidationError, jc.validate_completed_qty_matches_for_quantity)
		# completed + loss + pending == for_quantity -> passes
		jc.pending_qty = 4
		jc.validate_completed_qty_matches_for_quantity()

	def test_set_process_loss(self):
		jc = frappe.new_doc("Job Card")
		jc.for_quantity = 10
		jc.total_completed_qty = 6
		jc.pending_qty = 1
		jc.set_process_loss()
		self.assertEqual(jc.process_loss_qty, 3)  # 10 - 6 - 1

		# no loss when nothing completed yet
		nothing_done = frappe.new_doc("Job Card")
		nothing_done.for_quantity = 10
		nothing_done.total_completed_qty = 0
		nothing_done.set_process_loss()
		self.assertEqual(nothing_done.process_loss_qty, 0)

		all_process_loss = frappe.new_doc("Job Card")
		all_process_loss.for_quantity = 10
		all_process_loss.process_loss_qty = 10
		all_process_loss.set_process_loss()
		self.assertEqual(all_process_loss.process_loss_qty, 10)

	def test_zero_completed_qty_is_valid_for_semi_finished_goods(self):
		jc = frappe.new_doc("Job Card")
		jc.docstatus = 1
		jc.track_semi_finished_goods = 1
		jc.process_loss_qty = 5
		jc.validate_semi_finished_goods()

	def test_capacity_overlap_detection(self):
		jc = frappe.new_doc("Job Card")
		sequential = [
			{"from_time": "2026-01-01 10:00:00", "to_time": "2026-01-01 11:00:00"},
			{"from_time": "2026-01-01 11:00:00", "to_time": "2026-01-01 12:00:00"},
		]
		overlapping = [
			{"from_time": "2026-01-01 10:00:00", "to_time": "2026-01-01 11:00:00"},
			{"from_time": "2026-01-01 10:30:00", "to_time": "2026-01-01 11:30:00"},
		]
		# sequential logs share one capacity slot; overlapping logs need two
		self.assertEqual(len(jc.get_alloted_capacity(sequential)), 1)
		self.assertEqual(len(jc.get_alloted_capacity(overlapping)), 2)
		# capacity 1 overlaps with any log; capacity 2 only when both slots are taken
		self.assertTrue(jc.has_overlap(1, sequential))
		self.assertFalse(jc.has_overlap(2, sequential))
		self.assertTrue(jc.has_overlap(2, overlapping))

	def test_previous_operation_shortfall_from_process_loss_gets_the_right_message(self):
		jc = frappe.new_doc("Job Card")
		jc.operation = "_Test Painting"
		jc.stock_uom = "Nos"
		row = frappe._dict(
			operation="_Test Assembly", manufactured_qty=8, process_loss_qty=2, finished_good=None
		)

		with self.assertRaises(OperationSequenceError) as loss_error:
			jc.validate_previous_operation_manufactured_qty(row, 10)
		self.assertIn("process loss", str(loss_error.exception))

		row.process_loss_qty = 0
		with self.assertRaises(OperationSequenceError) as pending_error:
			jc.validate_previous_operation_manufactured_qty(row, 10)
		self.assertIn("Submit the manufacturing entry", str(pending_error.exception))

		jc.validate_previous_operation_manufactured_qty(row, 8)

	def test_semi_fg_job_card_is_exempt_from_transfer_qty_check(self):
		jc = frappe.new_doc("Job Card")
		jc.track_semi_finished_goods = 1
		jc.skip_material_transfer = 1
		jc.for_quantity = 10
		jc.transferred_qty = 0
		jc.append("items", {"item_code": "_Test Item"})

		jc.validate_transfer_qty()

		# with transfer enabled, a legacy card without an FG item keeps the strict check
		jc.skip_material_transfer = 0
		self.assertRaises(frappe.ValidationError, jc.validate_transfer_qty)

		jc.finished_good = "_Test Item"
		jc.validate_transfer_qty()

		jc.finished_good = None
		jc.track_semi_finished_goods = 0
		self.assertRaises(frappe.ValidationError, jc.validate_transfer_qty)
>>>>>>> 1d8ce1e (fix(stock): allow zero completed quantity and handle process loss in job cards (#59104))
