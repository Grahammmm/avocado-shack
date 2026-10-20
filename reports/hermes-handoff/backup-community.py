"""Create a consistent private community database backup; never sends data."""
import argparse, datetime, os, sqlite3
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--database',default=os.environ.get('AVOSHACK_COMMUNITY_DB'));parser.add_argument('--destination',required=True);args=parser.parse_args()
if not args.database: parser.error('Set AVOSHACK_COMMUNITY_DB or --database')
source=Path(args.database).resolve();target=Path(args.destination).resolve()
if source==target:parser.error('Backup destination must differ from source')
if target.exists():parser.error('Choose a new backup filename; existing backup will not be overwritten')
target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
try:
 with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as src:
  with sqlite3.connect(str(target)) as dst:
   src.backup(dst)
   if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Backup integrity check failed')
 os.chmod(target,0o600)
 print('Verified private database backup:',target)
except Exception:
 if target.exists():target.unlink()
 raise
