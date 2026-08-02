export class FeatureFlags {
  async isEnabled(_name: string): Promise<boolean> {
    return true;
  }
}
