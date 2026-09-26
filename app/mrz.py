"""ICAO TD1/TD3 checks: checksum validation is not document authentication."""
import re

def check_digit(text):
    def value(c):return int(c) if c.isdigit() else (ord(c)-55 if 'A'<=c<='Z' else 0)
    return str(sum(value(c)*[7,3,1][i%3] for i,c in enumerate(text))%10)

def parse(lines):
    candidates=[re.sub(r'[^A-Z0-9<]','',s.upper()) for s in lines]
    for i in range(len(candidates)-2):
        a,b,c=candidates[i:i+3]
        if len(a)!=30 or len(b)!=30 or len(c)!=30 or not a.startswith(('IDIRQ','I<IRQ')):continue
        checks={'document_number':check_digit(a[5:14])==a[14],'birth_date':check_digit(b[:6])==b[6],'expiry_date':check_digit(b[8:14])==b[14]}
        checks['composite']=check_digit(a[5:30]+b[:7]+b[8:15]+b[18:29])==b[29]
        return {'format':'TD1','valid':all(checks.values()) and b[7] in 'MF<' and b[15:18]=='IRQ','checks':checks,'document_number':a[5:14].rstrip('<'),'birth_yymmdd':b[:6],'expiry_yymmdd':b[8:14],'latin_name':' / '.join(' '.join(part.replace('<',' ').split()) for part in c.rstrip('<').split('<<',1)),'lines':[a,b,c]}
    return None
