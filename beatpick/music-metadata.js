ObjC.import('Foundation');
function run(argv) {
    const read = p => JSON.parse(ObjC.unwrap($.NSString.stringWithContentsOfFileEncodingError(p, $.NSUTF8StringEncoding, null)));
    const request = read(argv[1]);
    const music = Application('Music');
    const resolved = request.map(row => {
        const matches = music.libraryPlaylists[0].fileTracks.whose({persistentID: row.persistent_id})();
        if (matches.length !== 1) throw Error('Persistent ID is not unique: ' + row.persistent_id);
        const track = matches[0];
        const before = {persistent_id: track.persistentID(), title: track.name(), artist: track.artist(), album: track.album(), bpm: track.bpm(), comment: track.comment() || ''};
        for (const key of ['title', 'artist', 'album']) {
            if (before[key] !== row[key]) throw Error('Metadata changed: ' + row.persistent_id + ' / ' + key);
        }
        if (argv[0] === 'apply' && (before.bpm !== row.before.bpm || before.comment !== row.before.comment))
            throw Error('BPM/comment changed since preview: ' + row.persistent_id);
        return {track, before, row};
    });
    // Resolve and check the entire request before the first mutation.
    if (argv[0] === 'apply') {
        for (const item of resolved) {
            if (item.before.bpm !== item.row.after.bpm) item.track.bpm = item.row.after.bpm;
            if (item.before.comment !== item.row.after.comment) item.track.comment = item.row.after.comment;
        }
    } else if (argv[0] !== 'inspect') throw Error('Unknown mode');
    return JSON.stringify(resolved.map(x => ({...x.before, bpm: x.track.bpm(), comment: x.track.comment() || ''})));
}
