import sys

t = open('index.html').read()

# 1. origData backup
old1 = "const r=await fetch(API+'/api/v1/trends?limit=500',{headers:{'X-API-Key':KEY}});const j=await r.json();allData=j.data||[];"
new1 = "const r=await fetch(API+'/api/v1/trends?limit=500',{headers:{'X-API-Key':KEY}});const j=await r.json();allData=j.data||[];origData=allData.slice();"
if old1 in t:
    t = t.replace(old1, new1)
    print('1. origData backup added')
else:
    print('1. SKIP - fetch pattern not found')

# 2. origData var
if 'let allData=[]' in t and 'origData' not in t[:t.find('let allData=[]')+50]:
    t = t.replace('let allData=[]', 'let allData=[],origData=[]')
    print('2. origData var added')
else:
    print('2. SKIP or already exists')

# 3. Dynamic search function
dynamic_fn = """
async function dynamicSearch(query){
if(!query||query.length<2){allData=origData.slice();doFilter();return}
try{
var r2=await fetch(API+'/api/v2/feed?q='+encodeURIComponent(query)+'&limit=200',{headers:{'X-API-Key':KEY}});
var j2=await r2.json();
if(j2.data&&j2.data.length>0){allData=j2.data;doFilter()}
else{allData=origData.filter(function(t){return t.topicName.toLowerCase().includes(query.toLowerCase())||(t.summary||'').toLowerCase().includes(query.toLowerCase())});doFilter()}
}catch(e){allData=origData.filter(function(t){return t.topicName.toLowerCase().includes(query.toLowerCase())});doFilter()}}
"""

if 'dynamicSearch' not in t:
    t = t.replace('setInterval(load', dynamic_fn + '\nsetInterval(load')
    print('3. dynamicSearch function added')
else:
    print('3. SKIP - already exists')

# 4. Search input handler - replace client-side filter with dynamic API search
old_input = "document.getElementById('search').addEventListener('input',function(){searchTerm=this.value;doFilter()})"
new_input = "var searchTimer;document.getElementById('search').addEventListener('input',function(){searchTerm=this.value;clearTimeout(searchTimer);if(this.value.length>=2){searchTimer=setTimeout(function(){dynamicSearch(searchTerm)},500)}else if(this.value.length===0){allData=origData.slice();doFilter()}else{doFilter()}})"

if old_input in t:
    t = t.replace(old_input, new_input)
    print('4. Dynamic search handler added')
else:
    print('4. SKIP - search handler pattern not found')
    # Try to find what pattern exists
    idx = t.find("getElementById('search')")
    if idx > -1:
        print('   Found search element at pos', idx)
        print('   Context:', t[idx:idx+100])

open('index.html', 'w').write(t)
print('Done!')
