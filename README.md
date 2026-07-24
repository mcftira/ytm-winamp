# ytm-winamp

Play YouTube Music tracks and playlists in **classic Winamp** — the 2000s way.

Winamp 5.x can't talk to YouTube directly: the googlevideo CDN rejects its HTTP
client (`[access denied]` in the playlist, if you ever tried). `ytm-winamp`
bridges the gap with a tiny localhost server:

```
YouTube ──(yt-dlp)──▶ ffmpeg ──(MP3)──▶ http://127.0.0.1:8797 ──▶ Winamp
```

Winamp sees an ordinary MP3 web stream; yt-dlp and ffmpeg do the dirty work
behind the scenes. Tracks are transcoded to disk and upcoming queue entries
are prefetched in the background, so pressing **next** in Winamp starts the
following song in a fraction of a second instead of waiting for a cold
resolve — and googlevideo link expiry is never a problem, because stream
URLs are resolved when a track is downloaded, not when it is enqueued.

## Requirements

- Windows with [Winamp 5.x](https://www.winamp.com/player/) installed
- Python 3.10+
- [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) on your PATH
- [`ffmpeg`](https://ffmpeg.org/) on your PATH
- optional: [`ytmusicapi`](https://ytmusicapi.readthedocs.io) for playing
  your YouTube Music liked songs (`pip install .[liked]`)

## Install

```sh
pipx install .
pipx inject ytm-winamp ytmusicapi   # optional, for liked-songs support
# or: pip install .[liked]
```

## Usage

```sh
# default: play your YouTube Music liked songs (needs one-time auth, see below)
ytm-winamp

# ...shuffled
ytm-winamp liked --shuffle

# queue the top 5 search hits and play the best one
# (so Winamp's next/previous buttons have somewhere to go)
ytm-winamp play cheri cheri lady

# or just the top hit
ytm-winamp play cheri cheri lady -n 1

# play a specific video (YouTube or YouTube Music URL)
ytm-winamp play "https://music.youtube.com/watch?v=eNvUS-6PTbs"

# play a whole playlist
ytm-winamp play "https://music.youtube.com/playlist?list=PL..."

# list search results with URLs to pick from
ytm-winamp search modern talking -n 10

# run the bridge in the foreground (debugging)
ytm-winamp serve
```

On `play`, the bridge server starts itself in the background (once) and Winamp
opens with a playlist pointing at `127.0.0.1`. Track titles show up in the
Winamp playlist via `#EXTINF`, as nature intended.

## Liked songs: one-time auth setup

Reading your liked songs requires a YouTube Music login via `ytmusicapi`.
Run **one** of these once, then move the resulting file to
`%USERPROFILE%\.ytm-winamp\ytmusic.json`:

```sh
ytmusicapi oauth     # recommended; needs a Google Cloud OAuth client
                     # (see ytmusicapi.readthedocs.io for the steps)
ytmusicapi browser   # paste request headers copied from music.youtube.com
```

Pass a different location with `ytm-winamp liked --auth <path>`.

## Configuration

| Setting        | How                                                          |
| -------------- | ------------------------------------------------------------ |
| Winamp path    | set `YTM_WINAMP_EXE` if Winamp isn't in the default location |
| Bridge port    | `--port` (default `8797`)                                    |
| Bridge log     | `%TEMP%\ytm-winamp-bridge.log`                               |
| Track cache    | `%TEMP%\ytm-winamp-cache` (up to 32 tracks, LRU)             |
| YT Music auth  | `%USERPROFILE%\.ytm-winamp\ytmusic.json`                     |

## Roadmap

- [x] YouTube Music liked songs via `ytmusicapi` OAuth/browser auth
- [ ] Your other YouTube Music playlists by name
- [ ] ICY stream metadata so the title bar updates per track
- [ ] System tray controller
- [ ] Seeking support (needs Range requests in the bridge)

## Disclaimer

This is an unofficial hobby project, not affiliated with Winamp, YouTube, or
Google. It streams audio through [yt-dlp](https://github.com/yt-dlp/yt-dlp)
for personal playback; make sure your usage complies with YouTube's Terms of
Service and applicable law. Audio is cached temporarily on disk while you
listen (a rolling window of recent tracks, evicted automatically).

## License

MIT — see [LICENSE](LICENSE).
