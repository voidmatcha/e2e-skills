// SPDX-License-Identifier: Apache-2.0
export const visibleInvoices = invoices => invoices.filter(invoice => !invoice.paid);
