import sharp from 'sharp';import fs from 'node:fs/promises';import path from 'node:path';
const root=path.resolve(import.meta.dirname,'..');await fs.mkdir(path.join(root,'.runtime/media'),{recursive:true});
try{await sharp('/Users/owner/Desktop/IMG_4426.JPG').rotate().resize({width:1200,withoutEnlargement:true}).jpeg({quality:88}).toFile(path.join(root,'.runtime/media/michael.jpg'));console.log('Prepared supplied Michael portrait for private preview')}catch{console.log('Portrait unavailable; retain supplied store photo as fallback')}
