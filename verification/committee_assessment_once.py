"""One finite public evidence assessment; no ingestion, scheduling or app imports.

Fixed councils and12-month boundary. Reads official indexes, in-scope meeting
pages and only named reports needed for references/recommendations/supplements.
Raw pages/documents and personal fields are not retained. No transport retry.
"""
import argparse,hashlib,io,json,re,time
from datetime import date,datetime
from pathlib import Path
from urllib.parse import urljoin,urlsplit
import requests
from bs4 import BeautifulSoup
import pdfplumber

START=date(2025,10,14);END=date(2026,10,14)
MAX_LINKS=2000;MAX_DOCUMENTS=80;MAX_DOCUMENTS_FOLLOWED=3;MAX_COUNCIL_OUTPUT=2*1024*1024
ROOTS={
'bolton':'https://bolton.moderngov.co.uk/ieListMeetings.aspx?CommitteeId=140',
'bury':'https://councildecisions.bury.gov.uk/ieListMeetings.aspx?CommitteeId=134',
'manchester':'https://democracy.manchester.gov.uk/ieListMeetings.aspx?CommitteeId=151',
'oldham':'https://committees.oldham.gov.uk/ieListMeetings.aspx?CommitteeId=133',
'rochdale':'https://democracy.rochdale.gov.uk/mgCommitteeDetails.aspx?ID=674',
'salford':'https://sccdemocracy.salford.gov.uk/mgListCommittees.aspx?bcr=1',
'stockport':'https://democracy.stockport.gov.uk/ieListMeetings.aspx?CommitteeId=150',
'tameside':'https://tameside.moderngov.co.uk/ieListMeetings.aspx?CommitteeId=161',
'wigan':'https://wigan.moderngov.co.uk/ieListMeetings.aspx?CommitteeId=120&a=1'}
PATTERNS={
'bolton':r'\b\d{4,6}/(?:20)?\d{2}(?:/[A-Z]{1,8})?\b',
'bury':r'(?i)(?:App(?:lication)?\s*(?:No\.?|number)\s*[:.]?\s*)(\d{5,6})\b',
'manchester':r'\b\d{6}/[A-Z]{1,4}/20\d{2}\b',
'oldham':r'\b[A-Z]{2,5}/\d{6}/(?:20)?\d{2}\b',
'rochdale':r'\b\d{2}/\d{5}/[A-Z]{2,8}\b',
'salford':r'\b(?:[A-Z]{2,4}/20\d{2}/\d{4}|\d{2}/\d{5}/[A-Z]{2,8})\b',
'stockport':r'\bDC/?\d{6}\b',
'tameside':r'\b\d{2}/\d{5}/[A-Z]{2,8}\b',
'wigan':r'\bA/\d{2}/\d{5,6}/[A-Z]{2,8}\b'}
DATE_RE=r'\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+20\d{2})\b'


def normalize(ref):return ''.join(ref.upper().split())
def refs(text,council):
    found=sorted(set(re.findall(PATTERNS[council],text)))
    if len(found)>200:raise ValueError('reference mention cap')
    return found
def meeting_date(text):
    m=re.search(DATE_RE,text)
    return datetime.strptime(m.group(1),'%d %b %Y').date() if m else None

def role(label):
    t=label.lower()
    if any(x in t for x in ('supplement','update sheet','late representation','addendum')):return 'SUPPLEMENTARY_UPDATE'
    if 'minute' in t or 'decisions of this meeting' in t:return 'COMMITTEE_MINUTES'
    if 'agenda' in t and any(x in t for x in ('frontsheet','reports pack')):return 'AGENDA_PACK'
    if 'delegated decision' in t:return 'DELEGATED_DECISION_LIST'
    if 'appeal' in t:return 'APPEAL_REPORT'
    if any(x in t for x in ('site plan','location plan','map','drawing')):return 'OTHER_ATTACHMENT'
    if 'planning application' in t or 'report' in t or re.search(r'\b(?:\d{4,6}/|[A-Z]{1,5}/\d)',label):return 'OFFICER_REPORT'
    return 'UNKNOWN_DOCUMENT_TYPE'


def signals(text,kind):
    low=text.lower();out=[]
    if kind=='OFFICER_REPORT':
        for literal in ('Minded to Approve','Approve with Conditions','Recommend Approval','Recommend Refusal','Recommendation: Approve','Recommendation: Refuse'):
            if literal.lower() in low:out.append({'literal':re.search(re.escape(literal),text,re.I).group(0),'classification':'RECOMMEND_REFUSAL' if 'refus' in literal.lower() else 'RECOMMEND_APPROVAL'})
    if kind=='COMMITTEE_MINUTES':
        for term,cls in (('resolved to approve','RESOLVED_TO_APPROVE'),('minded to approve','MINDED_TO_APPROVE_MENTION_NON_FINAL'),('approved with conditions','APPROVED'),('refused','REFUSED'),('deferred','DEFERRED'),('withdrawn from the agenda','WITHDRAWN_FROM_AGENDA')):
            if term in low:out.append({'literal':re.search(re.escape(term),text,re.I).group(0),'classification':cls})
        if any(x in low for x in ('section 106','s106','s.106')):out.append({'literal':re.search(r'section 106|s106|s\.106',text,re.I).group(0),'classification':'S106_CONTEXT_REQUIRES_APPLICATION_ASSOCIATION'})
    return out


class Reader:
    def __init__(self):
        self.session=requests.Session();self.session.trust_env=False
        self.session.mount('https://',requests.adapters.HTTPAdapter(max_retries=0))
        self.started=time.monotonic();self.requests=0;self.bytes=0;self.last=0;self.audit=[];self.blocked=set();self.access_failures={}
    def get(self,url,council,pdf=False):
        host=urlsplit(ROOTS[council]).netloc
        allowed={host}
        if council=='wigan':allowed.add('democracy.wigan.gov.uk')
        u=urlsplit(url)
        if u.scheme!='https' or u.netloc not in allowed or u.username or u.password or u.fragment or len(url)>4096:raise ValueError('unadmitted source')
        if pdf:
            if not (u.path.startswith('/documents/') and u.path.lower().endswith('.pdf') or u.path=='/mgConvert2PDF.aspx'):raise ValueError('unadmitted document path')
        elif u.path not in {'/ieListMeetings.aspx','/mgCommitteeDetails.aspx','/mgListCommittees.aspx','/ieListDocuments.aspx'}:raise ValueError('unadmitted page path')
        if u.netloc in self.blocked:raise ValueError('host safely stopped')
        if self.requests>=250 or self.bytes>=128*1024*1024 or time.monotonic()-self.started>=600:raise ValueError('assessment cap')
        time.sleep(max(0,.5-(time.monotonic()-self.last)));self.last=time.monotonic()
        self.requests+=1;row={'url':url,'council':council,'purpose':'NAMED_PDF' if pdf else 'OFFICIAL_PAGE','status':'UNKNOWN','bytes':0};self.audit.append(row)
        response=None;body=bytearray();limit=8*1024*1024 if pdf else 512000
        try:
            response=self.session.get(url,stream=True,allow_redirects=False,timeout=(3,8));row['http_status']=response.status_code
            if response.status_code!=200:
                prefix=next(response.iter_content(4096),b'')
                self.bytes+=len(prefix);row['bytes']=len(prefix)
                if re.search(br'verify you are human|checking your browser|automated traffic|captcha',prefix,re.I):
                    self.blocked.add(u.netloc);raise ValueError('ACCESS_CONTROL_STOP')
                raise ValueError('HTTP_'+str(response.status_code))
            if 'attachment' in response.headers.get('Content-Disposition','').lower() and not pdf:raise ValueError('unexpected attachment')
            for chunk in response.iter_content(65536):
                body.extend(chunk)
                measured=max(len(body),response.raw.tell() if hasattr(response.raw,'tell') else 0)
                self.bytes+=measured-row['bytes'];row['bytes']=measured
                if measured>limit or self.bytes>128*1024*1024 or time.monotonic()-self.started>=600:raise ValueError('response cap')
            row['sha256']=hashlib.sha256(body).hexdigest();row['status']='READ'
            if pdf:
                if not body.startswith(b'%PDF'):raise ValueError('PDF shape')
                with pdfplumber.open(io.BytesIO(body)) as doc:
                    if len(doc.pages)>100:raise ValueError('PDF page cap')
                    text='\n'.join(page.extract_text() or '' for page in doc.pages)
                    if len(text)>1_000_000:raise ValueError('text cap')
                    row['pages']=len(doc.pages)
                return text,row
            encoding=response.encoding or 'utf-8';text=bytes(body).decode(encoding,errors='strict')
            if re.search(r'verify you are human|checking your browser|automated traffic|captcha',text[:8000],re.I):
                self.blocked.add(u.netloc);raise ValueError('ACCESS_CONTROL_STOP')
            return text,row
        except Exception as e:
            row['status']='FAILED';row['failure']=type(e).__name__+':'+str(e)[:80]
            if isinstance(e,(requests.Timeout,requests.ConnectionError)) or str(e).startswith('HTTP_'):
                self.access_failures[u.netloc]=self.access_failures.get(u.netloc,0)+1
                if self.access_failures[u.netloc]>=3:self.blocked.add(u.netloc)
            raise
        finally:
            if response is not None:response.close()
            body.clear()
    def close(self):self.session.close()


def source_links(soup,url):
    if len(soup.find_all('a',href=True,limit=MAX_LINKS+1))>MAX_LINKS:raise ValueError('link cap: INCOMPLETE')
    return [(a.get_text(' ',strip=True),urljoin(url,a.get('href','')),(a.find_parent('li') or a).get_text(' ',strip=True)) for a in soup.find_all('a',href=True)]


def assess(reader,council,checkpoint=lambda d:None):
    out={'council':council,'root':ROOTS[council],'coverage':'UNKNOWN','meetings':[],'gaps':[],
         'future_meetings':[],'publication_rule':'PUBLICATION_RULE_UNKNOWN','publication_timing':'UNKNOWN','additional_committee_scope':'NOT_YET_RECONCILED'}
    url=ROOTS[council]
    try:
        text,meta=reader.get(url,council);soup=BeautifulSoup(text,'html.parser')
        if council=='salford':
            candidates=[href for label,href,_ in source_links(soup,url) if label=='Planning and Transportation Regulatory Panel']
            if len(candidates)!=1:raise ValueError('panel identity')
            url=candidates[0];text,meta=reader.get(url,council);soup=BeautifulSoup(text,'html.parser')
        if 'mgCommitteeDetails.aspx' in url:
            candidates=[href for label,href,_ in source_links(soup,url) if label=='Browse meetings and agendas for this committee']
            if len(candidates)!=1:raise ValueError('browse identity')
            url=candidates[0];text,meta=reader.get(url,council);soup=BeautifulSoup(text,'html.parser')
        out['browse_url']=url
        out['committee_name']=(soup.select('h2')[0].get_text(' ',strip=True) if soup.select('h2') else 'UNKNOWN')
        out['calendar_urls']=[href for label,href,_ in source_links(soup,url) if label in ('Calendar','Meetings Calendar','Calendar of meetings')]
        out['identity_qualification']='EXTRACTED_MENTIONS_REQUIRE_PRINCIPAL_APPLICATION_QUALIFICATION_BEFORE_COMPARISON'
        meetings={};spanned=False
        for _ in range(3):
            dates=[]
            for label,href,parent in source_links(soup,url):
                day=meeting_date(label)
                if day is None or 'ieListDocuments.aspx' not in href:continue
                dates.append(day)
                if START<=day<END:meetings[href]={'date':day.isoformat(),'url':href,'cancelled':'CANCELLED' in parent,'training':'Training' in parent or 'Training' in label}
                elif day>=END:out['future_meetings'].append({'date':day.isoformat(),'label':label,'url':href})
            if dates and min(dates)<START:spanned=True;break
            earlier=[href for label,href,_ in source_links(soup,url) if label=='Earlier meetings']
            if len(earlier)!=1:break
            url=earlier[0];text,meta=reader.get(url,council);soup=BeautifulSoup(text,'html.parser')
        out['index_spans_start']=spanned
        if len(meetings)>30:raise ValueError('meeting cap')
        for record in sorted(meetings.values(),key=lambda x:x['date']):
            record.update(documents=[],references=[],agenda_publication_date='UNKNOWN',minutes_publication_date='UNKNOWN',inspection='NOT_INSPECTED')
            out['meetings'].append(record);checkpoint(out)
            if record['cancelled'] or record['training']:record['inspection']='EXCLUDED_CANCELLED_OR_TRAINING';continue
            try:
                html,meta=reader.get(record['url'],council);page=BeautifulSoup(html,'html.parser')
                main=page.find(id='modgov') or page.find(class_='mgContent') or page
                body=main.get_text(' ',strip=True)
                record['body_fingerprint']=meta['sha256'];record['inspection']='INSPECTED_HTML'
                record['references']=refs(body,council)
                record['unassociated_signal_mentions']=signals(body,'COMMITTEE_MINUTES') if 'Minutes:' in body else []
                links=source_links(main,record['url']);selected=[]
                for label,href,_ in links:
                    if '.pdf' not in href.lower() and 'mgConvert2PDF' not in href:continue
                    kind=role(label)
                    if len(record['documents'])>=MAX_DOCUMENTS:raise ValueError('document record cap: INCOMPLETE')
                    record['documents'].append({'label':label[:100] if kind in ('SUPPLEMENTARY_UPDATE','COMMITTEE_MINUTES','AGENDA_PACK') else kind,'url':href,'type':kind,'publication_date':'UNKNOWN','inspected':False})
                    # Do not fetch packs, maps, plans, appeals or contacts. Only the
                    # named compact application index and supplementary evidence.
                    if (council=='bury' and re.match(r'^Planning Applications\b',label)) or kind=='SUPPLEMENTARY_UPDATE':selected.append((label,href,kind))
                if len(selected)>MAX_DOCUMENTS_FOLLOWED:record['gap']='selected document cap: INCOMPLETE'
                for label,href,kind in selected[:MAX_DOCUMENTS_FOLLOWED]:
                    doc=next(x for x in record['documents'] if x['url']==href)
                    try:
                        pdf,pm=reader.get(href,council,pdf=True);doc.update(inspected=True,sha256=pm['sha256'],pages=pm['pages'],references=refs(pdf,council),unassociated_signal_mentions=signals(pdf,kind))
                        record['references']=sorted(set(record['references'])|set(doc['references']))
                        # Only explicit Bury indexed AppNo sections may bind unit
                        # scale/recommendation to an application. No global max.
                        if council=='bury' and kind=='OFFICER_REPORT':
                            sections=re.split(r'(?i)App\s*No\.?\s*(\d{5,6})',pdf)
                            details=[]
                            for i in range(1,len(sections)-1,2):
                                ref=sections[i];part=sections[i+1]
                                unit=re.search(r'(?i)\b(\d+)\s*(?:no\.?\s*)?(?:dwellings|apartments|flats)\b',part)
                                rec=re.search(r'(?i)Recommendation:\s*([^\n]+)',part)
                                details.append({'reference':ref,'unit_mention':int(unit.group(1)) if unit else None,'metric':'UNQUALIFIED_LITERAL' if unit else 'UNKNOWN','unit_scope':'UNIT_SCOPE_UNKNOWN','recommendation_literal':rec.group(1).split('Site Visit')[0].strip()[:80] if rec else 'UNKNOWN'})
                            doc['indexed_application_details']=details
                    except Exception as e:doc['gap']=str(e)[:100]
                    checkpoint(out)
            except Exception as e:record['inspection']='ACCESS_GAP';record['gap']=str(e)[:100]
            checkpoint(out)
        out['main_committee_html_coverage']='COMPLETE' if spanned and all(r['inspection']!='ACCESS_GAP' for r in out['meetings']) else 'INCOMPLETE'
        out['coverage']='INCOMPLETE'
        out['future_meetings']=sorted({r['url']:r for r in out['future_meetings']}.values(),key=lambda x:x['date'])
    except Exception as e:out['gaps'].append(str(e)[:100]);out['coverage']='UNKNOWN'
    return out


def bounded_checkpoint(path,data):
    serialized=json.dumps(data,indent=2,sort_keys=True)+'\n'
    if len(serialized.encode('utf-8'))>MAX_COUNCIL_OUTPUT:
        raise ValueError('serialized output cap: INCOMPLETE; prior checkpoint preserved')
    path.write_text(serialized)


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    import os
    if any(k in os.environ for k in ('DATABASE_URL','OPENAI_API_KEY','ANTHROPIC_API_KEY')):raise ValueError('credential-free only')
    if a.output.exists():raise ValueError('existing output')
    import signal
    signal.signal(signal.SIGTERM,lambda *args:(_ for _ in ()).throw(SystemExit('supervised deadline')))
    a.output.mkdir();reader=Reader()
    try:
        for council in ROOTS:
            d=assess(reader,council,lambda d:bounded_checkpoint(a.output/(council+'.json'),d)); bounded_checkpoint(a.output/(council+'.json'),d)
    finally:
        reader.close();audit={'requests':reader.requests,'bytes':reader.bytes,'elapsed_seconds':round(time.monotonic()-reader.started,3),'cleanup':'SESSION_CLOSED','production_mutation':False,'model_calls':0,'limits':{'requests':250,'bytes':128*1024*1024,'deadline_seconds':600,'meetings_per_council':30,'links_per_page':MAX_LINKS,'documents_per_meeting':MAX_DOCUMENTS,'documents_followed_per_meeting':MAX_DOCUMENTS_FOLLOWED,'references_per_document':200,'council_output_bytes':MAX_COUNCIL_OUTPUT},'records':reader.audit}
        (a.output/'resource.json').write_text(json.dumps(audit,indent=2,sort_keys=True)+'\n')
if __name__=='__main__':main()
