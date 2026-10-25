"""Shared, exact export sizes; the GUI and validation use the same mapping."""
RESOLUTIONS={
 'Landscape':[(1280,720),(1920,1080),(2560,1440),(3840,2160)],
 'Portrait':[(720,1280),(1080,1920),(1440,2560),(2160,3840)],
}


def validate_resolution(w,h):
    w,h=int(w),int(h)
    if not (2<=w<=8192 and 2<=h<=8192) or w%2 or h%2:
        raise ValueError('Width and height must be even numbers between 2 and 8192')
    return w,h
