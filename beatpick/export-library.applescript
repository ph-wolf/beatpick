on run argv
set exportPath to item 1 of argv
tell application "Music"
set trackIds to database ID of (every file track of library playlist 1)
set trackPids to persistent ID of (every file track of library playlist 1)
set trackNames to name of (every file track of library playlist 1)
set trackArtists to artist of (every file track of library playlist 1)
set trackAlbums to album of (every file track of library playlist 1)
set trackLocs to location of (every file track of library playlist 1)
set trackDurations to duration of (every file track of library playlist 1)
end tell
set rows to ""
repeat with i from 1 to count trackIds
try
set p to POSIX path of (item i of trackLocs)
set rows to rows & (item i of trackIds) & tab & (item i of trackPids) & tab & (item i of trackNames) & tab & (item i of trackArtists) & tab & (item i of trackAlbums) & tab & (item i of trackDurations) & tab & p & linefeed
end try
end repeat
set targetFile to open for access POSIX file exportPath with write permission
set eof targetFile to 0
write rows to targetFile as «class utf8»
close access targetFile
return count paragraphs of rows

end run
