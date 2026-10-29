const key=location.pathname.split('/').pop();
async function show(){
  try{
    const response=await fetch(`/api/knowledge/${encodeURIComponent(key)}/document`,{cache:'no-store'});
    const data=await response.json();if(!response.ok)throw Error(data.error||'无法打开文档');
    document.getElementById('title').textContent=data.title;document.title=data.title;
    document.getElementById('status').textContent=data.message||'';
    if(data.status==='processing'){setTimeout(show,1500);return;}
    if(data.status!=='ready')return;
    document.getElementById('status').textContent='';
    for(let i=1;i<=data.pages;i++){
      const image=document.createElement('img');image.src=`/api/knowledge/${encodeURIComponent(key)}/page/${i}`;
      image.alt=`第 ${i} 页`;image.loading=i>2?'lazy':'eager';image.decoding='async';document.getElementById('pages').append(image);
    }
  }catch(error){document.getElementById('status').textContent=error.message;}
}
show();
