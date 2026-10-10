type Song = { id: string; title: string; liked: boolean };

export function SongCard({ song, tab }: { song: Song; tab: 'all' | 'liked' }) {
  if (tab === 'liked' && !song.liked) {
    return null;
  }
  return <li data-testid="song-card">{song.title}</li>;
}
