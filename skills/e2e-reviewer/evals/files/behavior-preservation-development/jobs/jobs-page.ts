// SPDX-License-Identifier: Apache-2.0
export class JobsPage {
  constructor(page) { this.page = page; }
  async start() { await this.page.getByTestId('start-job-a').click(); }
  completion() { return this.page.getByText('Done', { exact: true }); }
}
