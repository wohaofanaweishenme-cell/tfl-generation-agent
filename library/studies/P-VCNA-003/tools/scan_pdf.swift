import Foundation
import PDFKit
import AppKit
let doc = PDFDocument(url:URL(fileURLWithPath:CommandLine.arguments[1]))!
var pages:[[String:Any]]=[]
for i in 0..<doc.pageCount {
 let p=doc.page(at:i)!, b=p.bounds(for:.mediaBox), t=p.string ?? ""
 pages.append(["page":i+1,"width":b.width,"height":b.height,"text":t])
 let image=p.thumbnail(of:NSSize(width:b.width,height:b.height),for:.mediaBox)
 let data=NSBitmapImageRep(data:image.tiffRepresentation!)!.representation(using:.png,properties:[:])!
 try! data.write(to:URL(fileURLWithPath:"identification_work/pages/page_\(i+1).png"))
}
try! JSONSerialization.data(withJSONObject:pages,options:[.prettyPrinted,.sortedKeys]).write(to:URL(fileURLWithPath:"identification_work/pages.json"))
print("Pages: \(doc.pageCount)")
