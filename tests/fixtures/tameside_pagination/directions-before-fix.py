def directions(soup,config,current):
    found={'NEXT':[],'PREVIOUS':[],'NUMBERED_NEXT':[]}
    for node in soup.select('a,button,input[type="submit"],input[type="button"],[role="button"],[onclick]'):
        label=' '.join((node.get('value','') if node.name=='input' else node.get_text(' ',strip=True)).split()).casefold()
        aria=node.get('aria-label','').strip().casefold();rel=node.get('rel',[]);classes=node.get('class',[])
        kind='NEXT' if label in ('next','next page','next >','next »','>','»') or aria in ('next','next page') or 'next' in rel or 'next' in classes else 'PREVIOUS' if label in ('previous','prev','previous page','<','«') or aria in ('previous','previous page') or 'prev' in rel or 'previous' in rel or 'prev' in classes or 'previous' in classes else None
        if kind is None:
            if label in ('load more','more results','more applications'):raise CalibrationError('CALIBRATION_NAVIGATION_UNSUPPORTED')
            if node.name=='a' and not disabled(node):
                q=parse_qs(urlsplit(node.get('href','')).query)
                values=q.get('searchCriteria.page',[])
                paging='searchCriteria.page' in q or urlsplit(node.get('href','')).path.endswith('/pagedSearchResults.do') or urlsplit(node.get('href','')).path=='pagedSearchResults.do'
                if paging and label.isdigit() and len(label)<=3 and int(label)>current:
                    require(int(label)==current+1,'CALIBRATION_NAVIGATION_AMBIGUOUS','NUMBERED_LINK_SKIPS_ADJACENT_PAGE')
                    kind='NUMBERED_NEXT'
                elif any(v.isdigit() and (len(v)>3 or int(v)>current) for v in values):
                    raise CalibrationError('CALIBRATION_NAVIGATION_AMBIGUOUS','UNCLASSIFIED_FORWARD_PAGE_LINK')
            if kind is None:continue
        e=dict(kind=kind,element=node.name,disabled=disabled(node),method=None,action_path=None,fields={},page=None)
        if not e['disabled']:
            expected=current+(1 if kind in ('NEXT','NUMBERED_NEXT') else -1)
            require(1<=expected<=7,'CALIBRATION_NAVIGATION_CONFLICT')
            if node.name=='a':
                href=node.get('href');require(type(href) is str and not node.has_attr('onclick'),'CALIBRATION_NAVIGATION_UNSUPPORTED')
                target=paging_get(href,config,expected)
                e.update(method='GET',action_path=urlsplit(target).path,fields={'action':'page','searchCriteria.page':str(expected)},page=expected)
                request=('GET',target,None)
            else:
                require(node.name in ('button','input'),'CALIBRATION_NAVIGATION_UNSUPPORTED')
                form=node.find_parent('form');require(form is not None and form.get('method','').upper()=='POST' and not any(node.has_attr(k) for k in ('onclick','formaction','formmethod','formenctype')),'CALIBRATION_NAVIGATION_UNSUPPORTED')
                target=urljoin(config.base+'/',form.get('action',''))
                require(target==config.base+'/pagedSearchResults.do','CALIBRATION_NAVIGATION_UNSUPPORTED')
                fields={}
                for field in form.select('input,select,textarea,button'):
                    if disabled(field):continue
                    typ=field.get('type','').lower();name=field.get('name','')
                    if field.name in ('button',) or typ in ('submit','button'):
                        if field is not node:continue
                        if not name:continue
                        value=field.get('value','')
                    elif field.name=='input' and typ=='hidden':value=field.get('value','')
                    elif field.name=='select':
                        options=field.select('option[selected]');require(len(options)==1,'CALIBRATION_NAVIGATION_AMBIGUOUS','POST_SELECT_NOT_SINGLE');value=options[0].get('value','')
                    else:raise CalibrationError('CALIBRATION_NAVIGATION_UNSUPPORTED')
                    require(name in {'_csrf','searchCriteria.page','action','orderBy','orderByDirection','searchCriteria.resultsPerPage'} and name not in fields and type(value) is str and len(value)<=1024,'CALIBRATION_NAVIGATION_UNSUPPORTED')
                    fields[name]=value
                require(fields.get('searchCriteria.page')==str(expected) and fields.get('action')=='page' and bool(fields.get('_csrf')),'CALIBRATION_NAVIGATION_CONFLICT')
                for k,v in [('orderBy','Reference'),('orderByDirection','Descending'),('searchCriteria.resultsPerPage','5')]:
                    require(k not in fields or fields[k]==v,'CALIBRATION_SORT_CHANGED')
                e.update(method='POST',action_path=urlsplit(target).path,fields=safe_controls(fields),page=expected)
                request=('POST',target,urlencode(fields).encode())
            found[kind].append((e,request))
        else:found[kind].append((e,None))
    summary={};next_request=None
    for kind,items in found.items():
        active=[x for x in items if not x[0]['disabled']]
        require(not active or len(active)==len(items),'CALIBRATION_NAVIGATION_CONFLICT')
        unique={x[1] for x in active};require(len(unique)<=1,'CALIBRATION_NAVIGATION_AMBIGUOUS','MULTIPLE_DISTINCT_DIRECTION_REQUESTS')
        summary[kind.lower()]=[x[0] for x in items]
        if kind=='NEXT' and active:next_request=active[0][1]
    # A numbered link can corroborate an explicit Next; it never authorises
    # navigation on its own. Reconcile after scanning both top/bottom pagers.
    numbered=[request for evidence,request in found['NUMBERED_NEXT'] if not evidence['disabled']]
    require(not numbered or next_request is not None,'CALIBRATION_NAVIGATION_AMBIGUOUS','NUMBERED_WITHOUT_EXPLICIT_NEXT')
    require(all(request==next_request for request in numbered),'CALIBRATION_NAVIGATION_CONFLICT')
    return summary,next_request
