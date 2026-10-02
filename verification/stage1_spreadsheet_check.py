"""Generate CSV projections and open them in local LibreOffice Calc."""
import json,subprocess,sys,tempfile,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.reporting.csv_safety import csv_bytes
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
values=['=1+1','+1+1','-1+1','@SUM(1,1)','\t=1+1','\r=1+1','\n=1+1','  =1+1','＝1+1','＋1','－1','＠SUM(1,1)','+44 1234 567890','https://www.bury.gov.uk/source','x,"quoted"\ntext',-5,42]
(out/'safety.csv').write_bytes(csv_bytes([{'id':i,'=header':v} for i,v in enumerate(values,1)],['id','=header']))
profile=Path(tempfile.mkdtemp(prefix='stage1-calc-'))
command=[sys.argv[2],'-env:UserInstallation='+profile.as_uri(),'--headless','--convert-to','xlsx','--outdir',str(out),str(out/'safety.csv')]
result=subprocess.run(command,capture_output=True,text=True,check=True);(out/'open.log').write_text(result.stdout+result.stderr)
ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
with zipfile.ZipFile(out/'safety.xlsx') as z:
 sheet=ET.fromstring(z.read('xl/worksheets/sheet1.xml'));strings=ET.fromstring(z.read('xl/sharedStrings.xml'))
 assert not sheet.findall('.//s:f',ns)
 cells={c.attrib['r']:c for c in sheet.findall('.//s:c',ns)}
 for index in range(1,17):assert cells['B'+str(index)].attrib['t']=='s'
 assert cells['B17'].find('s:v',ns).text=='-5' and cells['B18'].find('s:v',ns).text=='42'
 texts=[''.join(node.itertext()) for node in strings.findall('s:si',ns)]
 assert "'=header" in texts and "'=1+1" in texts and 'https://www.bury.gov.uk/source' in texts
(out/'result.json').write_text(json.dumps(dict(spreadsheet_open='LibreOffice Calc',formula_cells=0,hostile_text_and_header_preserved_as_text=True,negative_numeric_preserved=True,rows=17),indent=2))
print('PASS spreadsheet open: 17 fixture rows, zero formulas, numeric negatives preserved')
