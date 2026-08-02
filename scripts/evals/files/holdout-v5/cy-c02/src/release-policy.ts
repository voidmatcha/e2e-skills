export const releasePolicy = {
  only(channels: string[], active: string) {
    return channels.filter((channel) => channel === active);
  },
};
