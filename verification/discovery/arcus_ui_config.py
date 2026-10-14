"""Council differences observed through ordinary public search on14October2026.

Only frozen public listing URLs; no RPC construction or arbitrary input.
"""
from dataclasses import dataclass
import base64,json
from urllib.parse import urlencode
from .manchester_shape import DESTINATION, START, END

@dataclass(frozen=True)
class UIConfig:
    council: str
    destination: str
    blank_inputs: tuple
    blank_combos: tuple
    row_date: bool=True

    @property
    def host(self):return self.destination.split('/')[2]
    @property
    def aura(self):return 'https://'+self.host+'/pr/s/sfsites/aura'


def observed_url(host,fields,register_first=True):
    # Exact public URL search-filter shape observed after ordinary form submission.
    payload={'register':'Arcus_BE_Public_Register','requests':[{'registerName':'Arcus_BE_Public_Register',
        'searchType':'advanced','searchName':'Planning_Applications','advancedSearchName':'PA_ADV_All',
        'searchFilters':[{'fieldName':f,'fieldValue':v,'fieldDeveloperName':n} for f,v,n in fields]}]}
    q=base64.b64encode(json.dumps(payload,separators=(',',':')).encode()).decode()
    pairs=[('c__r','Arcus_BE_Public_Register'),('c__q',q)]
    if not register_first:pairs.reverse()
    return 'https://'+host+'/pr/s/register-view?'+urlencode(pairs)

COMMON=(('arcusbuiltenv__Proposal__c','','PA_ADV_Proposal'),('arcusbuiltenv__Status__c','','PA_ADV_ApplicationStatus'))
TYPE=('arcusbuiltenv__Type__c','','PA_ADV_ApplicationType')
DATES=(('arcusbuiltenv__Valid_Date__c',START,'PA_ADV_DateValidFrom'),('arcusbuiltenv__Valid_Date__c',END,'PA_ADV_DateValidTo'),
       ('arcusbuiltenv__Decision_Notice_Sent_Date_Manual__c','','PA_ADV_DecisionNoticeSentDateFrom'),
       ('arcusbuiltenv__Decision_Notice_Sent_Date_Manual__c','','PA_ADV_DecisionNoticeSentDateTo'))
WARD=('arcusbuiltenv__Wards__c','','PA_ADV_Ward')
MANCHESTER=UIConfig('manchester',DESTINATION,('Location of works','Description','Decision notice sent from','Decision notice sent to'),('Ward','Application Status','Record type','Application type'))
SALFORD=UIConfig('salford',observed_url('salfordcitycouncil.my.site.com',(('Salf_Site_Address__c','','PA_ADV_SiteAddress'),)+COMMON+(WARD,('arcusbuiltenv__PS_Scale__c','','PA_ADV_Application_Group'),TYPE)+DATES,False),
    ('Site Address','Description','Decision date from','Decision date to'),('Ward','Application Status','Application Category','Application type'),False)
ROCHDALE=UIConfig('rochdale',observed_url('account.rochdale.gov.uk',(('arcusbuiltenv__Site_Address__c','','PA_ADV_SiteAddress'),)+COMMON+(TYPE,)+DATES+(WARD,('arcusbuiltenv__Parishes__c','','PA_ADV_Parish'))),
    ('Location of works','Description','Decision notice was sent date from','Decision notice was sent date to'),('Ward','Application Status','Application type','Parish'))
UI_CASES={'discovery_'+c.council+'_ui_window':c for c in (MANCHESTER,SALFORD,ROCHDALE)}
