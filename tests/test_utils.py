"""Tests for utility functions."""

import pytest
from app.utils import (
    is_valid_url,
    is_playlist,
    sanitize_filename,
    format_duration,
    format_filesize,
    extract_video_id,
)


class TestIsValidUrl:
    """Test URL validation."""
    
    def test_youtube_watch_url(self):
        assert is_valid_url('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
        assert is_valid_url('https://youtube.com/watch?v=dQw4w9WgXcQ')
        assert is_valid_url('http://www.youtube.com/watch?v=dQw4w9WgXcQ')
    
    def test_youtube_short_url(self):
        assert is_valid_url('https://youtu.be/dQw4w9WgXcQ')
    
    def test_youtube_music_url(self):
        assert is_valid_url('https://music.youtube.com/watch?v=dQw4w9WgXcQ')
    
    def test_playlist_url(self):
        assert is_valid_url('https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf')
        assert is_valid_url('https://music.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf')
    
    def test_invalid_urls(self):
        assert not is_valid_url('')
        assert not is_valid_url(None)
        assert not is_valid_url('https://google.com')
        assert not is_valid_url('https://vimeo.com/12345')
        assert not is_valid_url('not a url')


class TestIsPlaylist:
    """Test playlist detection."""
    
    def test_playlist_urls(self):
        assert is_playlist('https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf')
        assert is_playlist('https://music.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf')
    
    def test_video_with_playlist(self):
        # Video URL with list parameter is treated as playlist
        assert is_playlist('https://www.youtube.com/watch?v=abc&list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf')
    
    def test_single_video_urls(self):
        assert not is_playlist('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
        assert not is_playlist('https://youtu.be/dQw4w9WgXcQ')
    
    def test_invalid_inputs(self):
        assert not is_playlist('')
        assert not is_playlist(None)


class TestSanitizeFilename:
    """Test filename sanitization."""
    
    def test_normal_filename(self):
        assert sanitize_filename('My Song Title') == 'My Song Title'
    
    def test_special_characters(self):
        assert sanitize_filename('Song: The Best?') == 'Song_ The Best_'
        assert sanitize_filename('A/B\\C') == 'A_B_C'
        assert sanitize_filename('test<>file') == 'test__file'
    
    def test_empty_input(self):
        assert sanitize_filename('') == 'untitled'
        assert sanitize_filename(None) == 'untitled'
    
    def test_max_length(self):
        long_title = 'A' * 300
        result = sanitize_filename(long_title, max_length=100)
        assert len(result) == 100
    
    def test_strip_dots_spaces(self):
        assert sanitize_filename('  song  ') == 'song'
        assert sanitize_filename('...song...') == 'song'


class TestFormatDuration:
    """Test duration formatting."""
    
    def test_seconds_only(self):
        assert format_duration(45) == '0:45'
    
    def test_minutes_seconds(self):
        assert format_duration(185) == '3:05'
        assert format_duration(60) == '1:00'
    
    def test_hours(self):
        assert format_duration(3661) == '1:01:01'
        assert format_duration(7200) == '2:00:00'
    
    def test_edge_cases(self):
        assert format_duration(0) == '0:00'
        assert format_duration(None) == '0:00'
        assert format_duration(-5) == '0:00'


class TestFormatFilesize:
    """Test filesize formatting."""
    
    def test_bytes(self):
        assert format_filesize(500) == '500.0 B'
    
    def test_kilobytes(self):
        assert format_filesize(1024) == '1.0 KB'
        assert format_filesize(2048) == '2.0 KB'
    
    def test_megabytes(self):
        assert format_filesize(1024 * 1024 * 5) == '5.0 MB'
    
    def test_edge_cases(self):
        assert format_filesize(0) == '0.0 B'
        assert format_filesize(None) == '0 B'


class TestExtractVideoId:
    """Test video ID extraction."""
    
    def test_watch_url(self):
        assert extract_video_id('https://www.youtube.com/watch?v=dQw4w9WgXcQ') == 'dQw4w9WgXcQ'
    
    def test_short_url(self):
        assert extract_video_id('https://youtu.be/dQw4w9WgXcQ') == 'dQw4w9WgXcQ'
    
    def test_with_extra_params(self):
        assert extract_video_id('https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10') == 'dQw4w9WgXcQ'
    
    def test_invalid_url(self):
        assert extract_video_id('https://google.com') is None
