export class FeatureFlags {
  isEnabled(name: string): boolean {
    return name.startsWith('account-');
  }
}
