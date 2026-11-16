function run() {
    const tracks = Application('Music').libraryPlaylists[0].fileTracks();
    return JSON.stringify(tracks.flatMap(t => {
        const location = t.location();
        if (!location) return [];
        return [{database_id: String(t.databaseID()), persistent_id: t.persistentID(),
            title: t.name(), artist: t.artist(), album: t.album(), genre: t.genre(),
            duration: t.duration(), path: location.toString()}];
    }));
}
