import Foundation
import PDFKit
let doc=PDFDocument(url:URL(fileURLWithPath:CommandLine.arguments[1]))!
var pages:[[String:Any]]=[]
for i in 0..<doc.pageCount {
 let p=doc.page(at:i)!, b=p.bounds(for:.mediaBox), t=p.string ?? "", ns=t as NSString
 var lines:[[String:Any]]=[];var start=0
 while start<ns.length {
  let r=ns.lineRange(for:NSRange(location:start,length:0));let s=ns.substring(with:r).trimmingCharacters(in:.newlines)
  if let sel=p.selection(for:r){let z=sel.bounds(for:p);lines.append(["text":s,"bbox":[z.minX,b.height-z.maxY,z.maxX,b.height-z.minY]])}
  start=NSMaxRange(r)
 }
 pages.append(["page":i+1,"lines":lines])
}
try! JSONSerialization.data(withJSONObject:pages,options:[.prettyPrinted,.sortedKeys]).write(to:URL(fileURLWithPath:"identification_work/lines.json"))
