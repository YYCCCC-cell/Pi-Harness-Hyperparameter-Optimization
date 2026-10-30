from pathlib import Path
import json
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
import pypdfium2 as pdfium
OUT=Path(__file__).resolve().parent; FIG=OUT/'figures';FIG.mkdir(exist_ok=True)
D=json.loads((OUT/'figure-input.json').read_text());S={'tasks':D['validation_tasks']}
LABEL={'default':'Default','random':'Random','bo':'BO','igbs':'IGBS'}
COLORS={'default':'#555555','random':'#356A9A','bo':'#B17823','igbs':'#8B4A75'}
def save(name,draw,w,h):
    c=canvas.Canvas(str(FIG/(name+'.pdf')),pagesize=(w,h));draw(c,w,h);c.save()
    pdfium.PdfDocument(FIG/(name+'.pdf'))[0].render(scale=2.5).to_pil().save(FIG/(name+'.png'))
def plot(c,w,h):
    c.setFillColor(HexColor('#222222'));c.setFont('Helvetica-Bold',14);c.drawString(25,h-23,'Validation incumbents on common supported budgets')
    for idx,axis in enumerate(['cumulative_known_usd','cumulative_committed_usd']):
        x=65+idx*310;y=60;pw=245;ph=220
        lo,hi=D['common_domains'][axis]
        c.setFont('Helvetica-Bold',10);c.drawString(x,y+ph+20,'Known token-cost estimate' if idx==0 else 'Known estimate plus reserve')
        c.setFont('Helvetica',8)
        for a in [0,.125,.25,.375,.5,.625,.75]:
            yy=y+a/.75*ph;c.setStrokeColor(HexColor('#DFDFDF'));c.setLineWidth(.5);c.line(x,yy,x+pw,yy)
            c.setFillColor(HexColor('#333333'));c.drawRightString(x-6,yy-3,f'{a:.1%}')
        for j in range(5):
            b=lo+(hi-lo)*j/4;c.drawCentredString(x+j*pw/4,y-13,f'${b:.2f}')
        c.drawCentredString(x+pw/2,y-30,'Cumulative USD')
        for m in ['default','random','bo','igbs']:
            pts=D['curves'][m];prev=[p for p in pts if p[axis]<=lo]
            if not prev:continue
            val=prev[-1]['incumbent_score'];seq=[(lo,val)]+[(p[axis],p['incumbent_score']) for p in pts if lo<p[axis]<=hi]+[(hi,None)]
            c.setStrokeColor(HexColor(COLORS[m]));c.setLineWidth(1.8);c.setDash(4,3) if m=='default' else c.setDash()
            xprev=lo;vprev=val
            for xx,v in seq[1:]:
                xp=x+(xprev-lo)/(hi-lo)*pw;xn=x+(xx-lo)/(hi-lo)*pw;yp=y+vprev/.75*ph;c.line(xp,yp,xn,yp)
                if v is not None:c.line(xn,yp,xn,y+v/.75*ph);vprev=v
                xprev=xx
        c.setDash();c.setFillColor(HexColor('#333333'));c.setFont('Helvetica',8)
        c.drawString(x+7,y+.25/.75*ph+7,'Random = IGBS at 25%' if idx==0 else 'Random = BO = IGBS at 25%')
        c.drawString(x+7,y+.375/.75*ph+7,'Default reference 37.5%')
        c.setDash();c.setStrokeColor(HexColor('#777777'));c.setLineWidth(.5);c.rect(x,y,pw,ph,stroke=1,fill=0)
    for i,m in enumerate(LABEL):
        x=80+i*150;c.setStrokeColor(HexColor(COLORS[m]));c.setLineWidth(2);c.line(x,22,x+20,22);c.setFillColor(HexColor('#222222'));c.setFont('Helvetica',9);c.drawString(x+26,19,LABEL[m])
def matrix(c,w,h):
    c.setFont('Helvetica-Bold',14);c.drawString(24,h-24,'Validation outcomes of the four frozen configurations')
    c.setFont('Helvetica',9);c.drawString(24,h-41,'Native verifier outcomes with measurement validity retained')
    names=['Financial modeling','Powerlifting','Prefix cache replay','Bike rebalance','3D scan calculation','Wyckoff analysis','Mario coin counting','Intrusion detection'];xx=190;cw=99;rh=27;top=h-76
    for j,m in enumerate(LABEL):c.setFont('Helvetica-Bold',10);c.drawCentredString(xx+j*cw+cw/2,top+10,LABEL[m])
    palette={'PASS':('#DCE8F2','#194A70'),'FAIL':('#F0F0F0','#555555'),'EXC':('#F7E7C9','#73511A')}
    for i,t in enumerate(S['tasks']):
        y=top-(i+1)*rh;c.setFillColor(HexColor('#222222'));c.setFont('Helvetica',10);c.drawRightString(xx-10,y+9,names[i])
        for j,m in enumerate(LABEL):
            st=D['winners'][m]['outcomes'][t];bg,fg=palette[st];c.setFillColor(HexColor(bg));c.setStrokeColor(HexColor('#FFFFFF'));c.rect(xx+j*cw,y,cw,rh,fill=1,stroke=1);c.setFillColor(HexColor(fg));c.setFont('Helvetica-Bold',9);c.drawCentredString(xx+j*cw+cw/2,y+9,st)
save('common-support-curves',plot,660,350)
save('frozen-validation-outcomes',matrix,620,310)
print('Saved two original scientific figures and source data')
