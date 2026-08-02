export class ReleaseChannel {
  only(channels: string[], selected: string) {
    return channels.filter((channel) => channel === selected);
  }
}
