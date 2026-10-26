"""Versioned source-depth pyramid, shared by preview resolutions; full map retained."""
import cv2

def level(depth,width,height,cache):
    key=id(depth)
    if key not in cache:
        cache.clear();h,w=depth.shape
        cache[key]=(depth,cv2.resize(depth,(max(1,w//2),max(1,h//2)),interpolation=cv2.INTER_AREA),cv2.resize(depth,(max(1,w//4),max(1,h//4)),interpolation=cv2.INTER_AREA))
    ratio=max(width/depth.shape[1],height/depth.shape[0])
    return cache[key][2 if ratio<=.25 else 1 if ratio<=.5 else 0]
