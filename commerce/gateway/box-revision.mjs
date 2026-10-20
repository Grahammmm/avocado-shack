export function revisionFields(source,version){
 if(!source||source.state!=='published')throw Object.assign(new Error('Choose a currently published box offer.'),{status:409});
 if(!Number.isSafeInteger(version)||source.version!==version)throw Object.assign(new Error('The box offer changed. Review its current version.'),{status:409});
 return structuredClone(source.fields);
}
