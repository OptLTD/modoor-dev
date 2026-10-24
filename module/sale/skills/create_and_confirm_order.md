---
id: sale.create_and_confirm_order
title: Create and confirm a sales order
summary: Draft a sales order then confirm it with human-in-the-loop.
when_to_use: |
  User wants to create a sales order / quotation and confirm it.
  Phase 0 uses partner and product_name strings (no partner/product modules yet).
tools:
  - sale.create_order
  - sale.get_order
  - sale.confirm_order
confirmations:
  - step: confirm
    tool: sale.confirm_order
    reason: Confirming commits the order; requires confirmation_token.
---

# Skill: Create and confirm sales order

## Steps

1. **Gather** customer name (`partner`) and line items (`product_name`, `qty`, `unit_price`).
2. Call **`sale.create_order`** with those fields. Expect `status=ok` and an `id`.
3. Optionally call **`sale.get_order`** with that `id` to verify totals.
4. Call **`sale.confirm_order`** with `order_id` only (no token yet).
5. If response is `status=needs_confirmation`:
   - Show `summary` to the human / host.
   - After approval, call **`sale.confirm_order` again** with the **same** `order_id` and the returned `confirmation_token`.
6. Expect `status=ok` and `state=confirmed`.

## 禁忌 / 边界

- Do **not** invent table schemas or write SQL.
- Do **not** skip confirmation for `sale.confirm_order`.
- Do **not** change `order_id` between the needs_confirmation response and the second call.
- Do **not** call unexported private APIs.
