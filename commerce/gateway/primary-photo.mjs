export function primaryPhoto(d,index=d.fields?._primary_photo_index){
 if(index===undefined)return d.photo;
 if(!Number.isSafeInteger(index)||index<0||!Array.isArray(d.photos)||index>=d.photos.length||typeof d.photos[index]?.photo!=='string'||!/^\/media\/(?:IMG_\d{4}|[a-f0-9-]+)\.jpg$/.test(d.photos[index].photo))throw Object.assign(new Error('Choose a photo from this update’s saved evidence.'),{status:422});
 return d.photos[index].photo;
}
