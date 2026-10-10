import type { APIRequestContext } from '@playwright/test';

export class BookingApi {
  constructor(private readonly request: APIRequestContext) {}

  async isWaitlisted(classId: string, member: string): Promise<boolean> {
    const response = await this.request.get(`/api/classes/${classId}/waitlist/${member}`);
    return response.ok() && (await response.json()).waitlisted === true;
  }
}
