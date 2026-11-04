# ledger

Small bookkeeping helpers.

Conventions (all modules must follow these):
- Money is stored as integer cents. Parse user input exactly; never lose a cent to floating point.
- Currency conversion rounds half-up to the nearest cent (0.5 cent rounds up), never banker's rounding.
- Statement pages are 1-indexed: page 1 is the first page.
