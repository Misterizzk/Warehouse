"""Small antialiased interface icons, drawn locally without image dependencies."""
from PIL import Image,ImageDraw,ImageTk


def icon(kind,size=28,color='#8CB9E9',master=None):
    scale=3
    image=Image.new('RGBA',(size*scale,size*scale))
    d=ImageDraw.Draw(image)
    def pts(values):return [(round(x*size*scale/32),round(y*size*scale/32)) for x,y in values]
    def line(values,width=2,fill=color):d.line(pts(values),fill=fill,width=round(width*size*scale/32),joint='curve')
    def box(rect,fill=None,width=2):d.rectangle(tuple(v*size*scale/32 for v in rect),fill=fill,outline=color,width=round(width*size*scale/32))
    if kind in ('warehouse','home'):
        d.polygon(pts([(2,12),(16,3),(30,12)]),fill=color)
        box((5,13,27,29))
        if kind=='warehouse':
            box((9,17,15,22),color);box((17,17,23,22),color);box((13,24,19,29),color)
        else:box((13,20,20,29),color)
    elif kind=='box':
        line([(3,9),(16,3),(29,9),(29,23),(16,30),(3,23),(3,9),(16,16),(29,9)])
        line([(16,16),(16,30)]);line([(9,6),(22,13)])
    elif kind=='check':
        d.ellipse((1*scale*size/32,1*scale*size/32,31*scale*size/32,31*scale*size/32),fill=color)
        line([(9,16),(14,21),(24,10)],3,'#09243B')
    elif kind=='warning':
        d.polygon(pts([(16,2),(31,29),(1,29)]),fill=color)
        line([(16,11),(16,19)],3,'#11253A');d.ellipse(tuple(v*size*scale/32 for v in (14.5,23,17.5,26)),fill='#11253A')
    elif kind=='alert':
        d.ellipse(tuple(v*size*scale/32 for v in (1,1,31,31)),fill=color)
        line([(16,8),(16,19)],3,'#11253A');d.ellipse(tuple(v*size*scale/32 for v in (14.5,23,17.5,26)),fill='#11253A')
    elif kind=='clipboard':
        box((6,6,26,30));box((11,3,21,9),'#10243A');line([(11,16),(22,16)]);line([(11,22),(20,22)])
    elif kind=='chart':
        line([(4,3),(4,29),(30,29)])
        box((9,17,13,25),color);box((17,11,21,25),color);box((25,5,29,25),color)
    elif kind=='scan':
        for p in [[(3,12),(3,3),(12,3)],[(20,3),(29,3),(29,12)],[(3,20),(3,29),(12,29)],[(20,29),(29,29),(29,20)]]:line(p)
        line([(8,16),(24,16)])
    elif kind=='file':
        line([(6,2),(20,2),(27,9),(27,30),(6,30),(6,2)])
        line([(20,2),(20,9),(27,9)]);line([(11,16),(22,16)]);line([(11,22),(22,22)])
    elif kind=='calendar':
        box((3,7,29,29));line([(3,13),(29,13)]);line([(10,2),(10,10)]);line([(23,2),(23,10)])
        for x,y in [(9,18),(17,18),(9,24),(17,24)]:box((x,y,x+2,y+2),color,1)
    return ImageTk.PhotoImage(image.resize((size,size),Image.Resampling.LANCZOS),master=master)
