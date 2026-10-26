"""Generate an honest checksum/signature inventory for Windows artifacts."""
import argparse,hashlib,json,subprocess
from datetime import datetime,timezone
from pathlib import Path

def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        while chunk:=stream.read(1024*1024):digest.update(chunk)
    return digest.hexdigest()

def signature(path):
    command=f"$s=Get-AuthenticodeSignature -LiteralPath '{str(path).replace("'","''")}';$s.Status.ToString()"
    result=subprocess.run(['powershell','-NoProfile','-Command',command],capture_output=True,text=True)
    return result.stdout.strip() if result.returncode==0 else 'Unavailable'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('artifacts',nargs='+');parser.add_argument('--output');args=parser.parse_args()
    rows=[]
    for value in args.artifacts:
        path=Path(value).resolve()
        if not path.is_file():raise SystemExit(f'Missing release artifact: {path}')
        rows.append({'path':str(path),'size_bytes':path.stat().st_size,'sha256':sha(path),'authenticode_status':signature(path)})
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'artifacts':rows,'production_signed':bool(rows) and all(r['authenticode_status']=='Valid' for r in rows)}
    rendered=json.dumps(report,indent=2)
    if args.output:Path(args.output).write_text(rendered+'\n',encoding='utf-8')
    print(rendered);return 0 if report['production_signed'] else 2
if __name__=='__main__':raise SystemExit(main())
