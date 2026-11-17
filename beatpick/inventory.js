function run() {
    const tracks = Application('Music').libraryPlaylists[0].fileTracks;
    // Read columns in batches rather than issuing seven IPC calls per track.
    const ids = tracks.databaseID();
    const pids = tracks.persistentID();
    const titles = tracks.name();
    const artists = tracks.artist();
    const albums = tracks.album();
    const genres = tracks.genre();
    const durations = tracks.duration();
    const locations = tracks.location();
    return JSON.stringify(ids.flatMap((id, i) => locations[i] ? [{
        database_id: String(id), persistent_id: pids[i], title: titles[i],
        artist: artists[i], album: albums[i], genre: genres[i],
        duration: durations[i], path: locations[i].toString()
    }] : []));
}
