# ytm-winamp

Play YouTube Music tracks and playlists in **classic Winamp** — the 2000s way.

Winamp 5.x can't talk to YouTube directly: the googlevideo CDN rejects its HTTP
client (`[access denied]` in the playlist, if you ever tried). `ytm-winamp`
bridges the gap with a tiny localhost server:

```
YouTube ──(yt-dlp)──▶ ffmpeg ──(MP3)──▶ http://127.0.0.1:8797 ──▶ Winamp
```

Winamp sees an ordinary MP3 web stream; yt-dlp and ffmpeg do the dirty work
behind the scenes. Stream URLs are resolved lazily when Winamp actually
requests a track, so googlevideo link expiry is never a problem.

## Requirements

- Windows with [Winamp 5.x](https://www.winamp.com/player/) installed
- Python 3.10+
- [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) on your PATH
- [`ffmpeg`](https://ffmpeg.org/) on your PATH

## Install

```sh
pipx install .
# or: pip install .
```

## Usage

```sh
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

## Configuration

| Setting        | How                                                          |
| -------------- | ------------------------------------------------------------ |
| Winamp path    | set `YTM_WINAMP_EXE` if Winamp isn't in the default location |
| Bridge port    | `--port` (default `8797`)                                    |
| Bridge log     | `%TEMP%\ytm-winamp-bridge.log`                               |

## Roadmap

- [ ] YouTube Music account integration (your library, likes and playlists) via `ytmusicapi` OAuth
- [ ] ICY stream metadata so the title bar updates per track
- [ ] System tray controller
- [ ] Seeking support

## Disclaimer

This is an unofficial hobby project, not affiliated with Winamp, YouTube, or
Google. It streams audio through [yt-dlp](https://github.com/yt-dlp/yt-dlp)
for personal playback; make sure your usage complies with YouTube's Terms of
Service and applicable law. No content is downloaded permanently — audio is
transcoded on the fly and never stored.

## License

MIT — see [LICENSE](LICENSE).
