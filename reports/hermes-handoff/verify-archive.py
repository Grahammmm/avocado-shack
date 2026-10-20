"""Verify a preserved handoff archive and every extracted regular file."""
from pathlib import Path
import hashlib,json
base=Path('/home/user/.local/share/avocado-shack');backup=base/'backups';archive=backup/'project-deduplicated.tar.gz'
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
 return h.hexdigest()
expected=(backup/'deduplicated-sha256.txt').read_text().split()[0]
actual=digest(archive);assert actual==expected,'Archive checksum mismatch'
manifest=json.loads((backup/'manifest.json').read_text());cache={};count=0;total=0
for item in manifest['files']:
 relative=Path(item['path']);assert not relative.is_absolute() and '..' not in relative.parts
 p=base/'mac-archive'/relative;s=p.stat();assert s.st_size==item['bytes'],str(relative)+' size mismatch'
 key=(s.st_dev,s.st_ino,s.st_size)
 if key not in cache:cache[key]=digest(p)
 assert cache[key]==item['sha256'],str(relative)+' checksum mismatch'
 count+=1;total+=s.st_size
result={'passed':True,'archiveSha256':actual,'archiveBytes':archive.stat().st_size,'verifiedFiles':count,'logicalBytes':total,'uniqueInodesHashed':len(cache),'excludedReproduciblePaths':manifest['excluded_reproducible_paths'],'sourceSnapshot':'Mac pre-migration source/data; active Git worktree is separately maintained'}
(base/'archive-verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
