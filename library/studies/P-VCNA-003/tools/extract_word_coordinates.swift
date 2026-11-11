import Foundation
import PDFKit
let doc=PDFDocument(url:URL(fileURLWithPath:CommandLine.arguments[1]))!
var pages:[[String:Any]]=[]
let rx=try! NSRegularExpression(pattern:"\\S+")
for i in 0..<doc.pageCount {
 let p=doc.page(at:i)!, b=p.bounds(for:.mediaBox), t=p.string ?? "", ns=t as NSString
 var words:[[String:Any]]=[]
 for m in rx.matches(in:t,range:NSRange(location:0,length:ns.length)) {
  if let sel=p.selection(for:m.range){let z=sel.bounds(for:p);words.append(["text":ns.substring(with:m.range),"bbox":[z.minX,b.height-z.maxY,z.maxX,b.height-z.minY],"source_offset_utf16":m.range.location,"source_length_utf16":m.range.length])}
 }
 pages.append(["page":i+1,"width_points":b.width,"height_points":b.height,"words":words])
}
try! JSONSerialization.data(withJSONObject:pages,options:[.prettyPrinted,.sortedKeys]).write(to:URL(fileURLWithPath:CommandLine.arguments[2]))
print("Extracted word bounds on \(doc.pageCount) pages")
