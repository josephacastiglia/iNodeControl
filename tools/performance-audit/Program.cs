using System.Reflection;
using System.Reflection.Emit;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

var opcodes=typeof(OpCodes).GetFields(BindingFlags.Public|BindingFlags.Static).Where(f=>f.FieldType==typeof(OpCode))
    .Select(f=>(OpCode)f.GetValue(null)!).ToDictionary(o=>unchecked((ushort)o.Value));
string Normalize(string s)=>Regex.Replace(s,@"d__\d+","d__");
Dictionary<string,string[]> Read(string path)
{
    using var stream=File.OpenRead(path);using var pe=new PEReader(stream);var r=pe.GetMetadataReader();
    string TypeName(TypeDefinitionHandle h){var t=r.GetTypeDefinition(h);return t.GetDeclaringType().IsNil?r.GetString(t.Namespace)+"."+r.GetString(t.Name):TypeName(t.GetDeclaringType())+"/"+r.GetString(t.Name);}
    string Resolve(EntityHandle h)=>h.Kind switch {
        HandleKind.TypeDefinition=>TypeName((TypeDefinitionHandle)h),
        HandleKind.TypeReference=>r.GetString(r.GetTypeReference((TypeReferenceHandle)h).Namespace)+"."+r.GetString(r.GetTypeReference((TypeReferenceHandle)h).Name),
        HandleKind.MethodDefinition=>TypeName(r.GetMethodDefinition((MethodDefinitionHandle)h).GetDeclaringType())+"::"+r.GetString(r.GetMethodDefinition((MethodDefinitionHandle)h).Name),
        HandleKind.FieldDefinition=>TypeName(r.GetFieldDefinition((FieldDefinitionHandle)h).GetDeclaringType())+"::"+r.GetString(r.GetFieldDefinition((FieldDefinitionHandle)h).Name),
        HandleKind.MemberReference=>Resolve(r.GetMemberReference((MemberReferenceHandle)h).Parent)+"::"+r.GetString(r.GetMemberReference((MemberReferenceHandle)h).Name),
        HandleKind.TypeSpecification=>"typespec:"+Convert.ToHexString(r.GetBlobBytes(r.GetTypeSpecification((TypeSpecificationHandle)h).Signature)),
        HandleKind.MethodSpecification=>Resolve(r.GetMethodSpecification((MethodSpecificationHandle)h).Method)+":"+Convert.ToHexString(r.GetBlobBytes(r.GetMethodSpecification((MethodSpecificationHandle)h).Signature)),
        HandleKind.StandaloneSignature=>"sig:"+Convert.ToHexString(r.GetBlobBytes(r.GetStandaloneSignature((StandaloneSignatureHandle)h).Signature)),
        _=>h.Kind.ToString()
    };
    var methods=new Dictionary<string,string[]>();
    foreach(var handle in r.MethodDefinitions)
    {
        var method=r.GetMethodDefinition(handle);if(method.RelativeVirtualAddress==0)continue;
        string key=Normalize(TypeName(method.GetDeclaringType())+"::"+r.GetString(method.Name))+"#"+method.GetParameters().Count;
        if(methods.ContainsKey(key))key+="/"+Convert.ToHexString(r.GetBlobBytes(method.Signature));
        byte[] il=pe.GetMethodBody(method.RelativeVirtualAddress).GetILBytes()!;var lines=new List<string>();
        for(int i=0;i<il.Length;)
        {
            ushort code=il[i++];if(code==0xfe)code=(ushort)(0xfe00|il[i++]);var op=opcodes[code];string operand="";
            if(op.OperandType is OperandType.InlineField or OperandType.InlineMethod or OperandType.InlineType or OperandType.InlineTok or OperandType.InlineSig or OperandType.InlineString)
            {
                int token=BitConverter.ToInt32(il,i);i+=4;
                operand=op.OperandType==OperandType.InlineString?r.GetUserString(MetadataTokens.UserStringHandle(token&0xffffff)):Resolve(MetadataTokens.EntityHandle(token));
                operand=Normalize(operand);
            }
            else
            {
                int count=op.OperandType switch {OperandType.InlineNone=>0,OperandType.ShortInlineBrTarget or OperandType.ShortInlineI or OperandType.ShortInlineVar=>1,
                    OperandType.InlineVar=>2,OperandType.InlineI8 or OperandType.InlineR=>8,OperandType.InlineSwitch=>4+4*BitConverter.ToInt32(il,i),_=>4};
                operand=Convert.ToHexString(il.AsSpan(i,count));i+=count;
            }
            lines.Add(op.Name+" "+operand);
        }
        methods[key]=lines.ToArray();
    }
    return methods;
}
var current=Read(args[0]);var results=new List<object>();
foreach(var baseline in args.Skip(2))
{
    var old=Read(baseline);
    var selected=old.Where(p=>p.Key.StartsWith("IMouse2.LiveFrame::") ||p.Key.StartsWith("IMouse2.FrameBuffer::") ||p.Key.StartsWith("IMouse2.JitterMeter::") ||
        p.Key.Contains("<PumpAsync>") ||p.Key.Contains("<TilePumpAsync>") ||p.Key.Contains("<ScreenshotIntoAsync>") ||p.Key.Contains("<DragLoopAsync>") ||p.Key.Contains("<PumpPointerAsync>") ||
        p.Key.Contains("::PresentPending") ||p.Key.Contains("::StartPump") ||p.Key.Contains("::Rate_Changed") ||p.Key.Contains("::WallRate_Changed") ||p.Key.Contains("::TrackPointerTo"));
    var rows=selected.Select(p=>new {method=p.Key,present=current.ContainsKey(p.Key),instructionsMatch=current.TryGetValue(p.Key,out var now)&&p.Value.SequenceEqual(now)}).ToArray();
    results.Add(new{baseline,sha256=Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(baseline))),methods=rows});
    foreach(var row in rows.Where(x=>x.present&&!x.instructionsMatch))
    {
        string file=Regex.Replace(Path.GetFileName(Path.GetDirectoryName(baseline))+"-"+row.method,@"[^A-Za-z0-9_.-]","_");
        Directory.CreateDirectory(Path.Combine(args[1],"differences"));
        File.WriteAllLines(Path.Combine(args[1],"differences",file+"-old.txt"),old[row.method]);
        File.WriteAllLines(Path.Combine(args[1],"differences",file+"-new.txt"),current[row.method]);
    }
}
Directory.CreateDirectory(args[1]);
File.WriteAllText(Path.Combine(args[1],"binary-comparison.json"),JsonSerializer.Serialize(new{current=args[0],sha256=Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(args[0]))),results},new JsonSerializerOptions{WriteIndented=true}));
Console.WriteLine(JsonSerializer.Serialize(results));
